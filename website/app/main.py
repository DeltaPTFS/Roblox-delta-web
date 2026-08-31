from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .database import Base, engine, get_db
from .models import AuditLog, Redemption, Reward, Status, Tier, TierConfig, Transaction, User
from .oauth import discord_authorize, discord_identity, roblox_authorize, roblox_identity
from .security import check_csrf, consume_oauth, csrf_token, current_user, oauth_values, permission
from .session import DatabaseSessionMiddleware

ROOT = Path(__file__).resolve().parents[1]
settings = get_settings()
templates = Jinja2Templates(directory=ROOT / "templates")
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        if not db.scalar(select(TierConfig.id).limit(1)):
            tier_defaults = [
                (Tier.MEMBER, 0, 0, 0, "Start earning toward Medallion Status with every eligible community journey.", ["Earn and redeem SkyMiles", "Member rewards catalog"]),
                (Tier.SILVER, 20000, 4000, 1, "The stepping stone to Medallion Status, with elevated recognition on eligible community trips.", ["Complimentary upgrade eligibility", "Priority boarding"]),
                (Tier.GOLD, 30000, 12000, 5, "Unlock a broader suite of priority services and recognition throughout the community.", ["Unlimited complimentary upgrade eligibility", "Sky Priority-style community services"]),
                (Tier.PLATINUM, 40000, 20000, 10, "The final step before Diamond, with customizable benefits and premium community recognition.", ["Unlimited complimentary upgrade eligibility", "Choice Benefits", "Priority services"]),
                (Tier.DIAMOND, 50000, 28000, 15, "Our highest roleplay Medallion tier, recognizing the community's most engaged travelers.", ["Highest upgrade priority", "Highest Medallion boarding priority", "Customizable Choice Benefits"]),
            ]
            for tier, miles, mqp, segments, description, benefits in tier_defaults:
                db.add(TierConfig(tier=tier, miles_threshold=miles, mqp_threshold=mqp, segments_threshold=segments, description=description, benefits=benefits))
            for name, desc, cost in [("Priority Boarding","Board first at a community flight.",2500),("Flight Upgrade","Upgrade an eligible roleplay itinerary.",5000),("Exclusive Discord Role","Unlock a distinguished community role.",10000),("Special Aircraft Access","Access a featured community aircraft.",15000)]: db.add(Reward(name=name, description=desc, miles_cost=cost, active=True))
            db.commit()
    yield


app = FastAPI(title="Delta SkyMiles | Roblox", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda r, e: JSONResponse({"detail":"Too many requests"}, 429))
app.add_middleware(DatabaseSessionMiddleware, secure=settings.cookie_secure, max_age=86400)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def context(request, **values): return {"request":request,"csrf":csrf_token(request),"settings":settings,**values}


@app.get("/health")
def health(): return {"status":"ok"}


@app.get("/", response_class=HTMLResponse)
def login(request: Request):
    if request.session.get("user_id"): return RedirectResponse("/dashboard", 303)
    return templates.TemplateResponse("login.html", context(request))


@app.get("/auth/roblox")
@limiter.limit("10/minute")
def start_roblox(request: Request):
    if not settings.roblox_client_id or not settings.roblox_group_id: raise HTTPException(503, "Roblox OAuth is not configured")
    state, challenge = oauth_values(request, "roblox")
    return RedirectResponse(roblox_authorize(settings, state, challenge))


@app.get("/auth/roblox/callback")
@limiter.limit("10/minute")
async def roblox_callback(request: Request, code: str, state: str, db: Session=Depends(get_db)):
    verifier = consume_oauth(request, "roblox", state)
    try: identity = await roblox_identity(settings, code, verifier)
    except Exception: return RedirectResponse("/error?kind=roblox", 303)
    if not identity["membership"]:
        request.session.clear(); return templates.TemplateResponse("restricted.html", context(request, kind="roblox"), status_code=403)
    role = identity["membership"]["role"]
    request.session["pending_roblox"] = {**identity, "membership":True, "role":role.get("name"), "rank":int(role.get("rank",0))}
    existing = db.scalar(select(User).where(User.roblox_user_id == identity["id"]))
    if existing:
        existing.roblox_username, existing.roblox_display_name, existing.roblox_avatar_url = identity["username"], identity["display_name"], identity["avatar"]
        existing.roblox_group_role, existing.roblox_group_rank = role.get("name"), int(role.get("rank",0)); db.commit()
        request.session["link_user_id"] = existing.id
    return RedirectResponse("/connect-discord", 303)


@app.get("/connect-discord", response_class=HTMLResponse)
def connect_discord(request: Request):
    pending = request.session.get("pending_roblox")
    if not pending: return RedirectResponse("/",303)
    return templates.TemplateResponse("connect.html", context(request, roblox=pending))


@app.get("/auth/discord")
@limiter.limit("10/minute")
def start_discord(request: Request):
    if not request.session.get("pending_roblox"): raise HTTPException(401, "Verify Roblox first")
    state, challenge = oauth_values(request, "discord")
    return RedirectResponse(discord_authorize(settings, state, challenge))


def next_number(db):
    last = db.scalar(select(User.skymiles_number).order_by(User.id.desc()).limit(1))
    return f"SM-{(int(last.split('-')[1]) + 1 if last else 1):08d}"


@app.get("/auth/discord/callback")
@limiter.limit("10/minute")
async def discord_callback(request: Request, code: str, state: str, db: Session=Depends(get_db)):
    pending = request.session.get("pending_roblox")
    if not pending: raise HTTPException(401, "Verification session expired")
    verifier = consume_oauth(request, "discord", state)
    try: identity = await discord_identity(settings, code, verifier)
    except Exception: return RedirectResponse("/error?kind=discord",303)
    if not identity["member"]: return templates.TemplateResponse("restricted.html", context(request, kind="discord"), status_code=403)
    existing_roblox = db.scalar(select(User).where(User.roblox_user_id == pending["id"]))
    existing_discord = db.scalar(select(User).where(User.discord_user_id == identity["id"]))
    if existing_discord and (not existing_roblox or existing_discord.id != existing_roblox.id): return templates.TemplateResponse("error.html", context(request, title="Account Already Linked", message="That Discord account is already linked to another SkyMiles membership."), status_code=409)
    user = existing_roblox
    if user:
        user.discord_user_id=identity["id"]; user.discord_username=identity["username"]; user.discord_display_name=identity["display_name"]; user.discord_avatar_url=identity["avatar"]; user.discord_role_ids=identity["member"].get("roles",[]); user.discord_verified_at=datetime.now(timezone.utc)
    else:
        user=User(roblox_user_id=pending["id"],roblox_username=pending["username"],roblox_display_name=pending["display_name"],roblox_avatar_url=pending["avatar"],roblox_group_role=pending["role"],roblox_group_rank=pending["rank"],discord_user_id=identity["id"],discord_username=identity["username"],discord_display_name=identity["display_name"],discord_avatar_url=identity["avatar"],discord_role_ids=identity["member"].get("roles",[]),skymiles_number=next_number(db),miles_balance=settings.welcome_bonus_miles,lifetime_miles=max(0,settings.welcome_bonus_miles))
        db.add(user)
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,"Account link conflict")
    db.refresh(user); request.session.clear(); request.session["user_id"]=user.id; request.session["authorization"]=permission(user,settings)
    return RedirectResponse("/dashboard",303)


def member_page(request: Request, template: str, db: Session):
    user=current_user(request,db); transactions=db.scalars(select(Transaction).where(Transaction.user_id==user.id).order_by(Transaction.created_at.desc()).limit(20)).all(); rewards=db.scalars(select(Reward).where(Reward.active.is_(True))).all(); tiers=db.scalars(select(TierConfig).order_by(TierConfig.miles_threshold)).all()
    return templates.TemplateResponse(template, context(request,user=user,transactions=transactions,rewards=rewards,tiers=tiers,auth=permission(user,settings)))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request:Request,db:Session=Depends(get_db)): return member_page(request,"dashboard.html",db)
@app.get("/miles", response_class=HTMLResponse)
def miles(request:Request,db:Session=Depends(get_db)): return member_page(request,"miles.html",db)
@app.get("/activity", response_class=HTMLResponse)
def activity(request:Request,db:Session=Depends(get_db)): return member_page(request,"activity.html",db)
@app.get("/rewards", response_class=HTMLResponse)
def rewards(request:Request,db:Session=Depends(get_db)): return member_page(request,"rewards.html",db)
@app.get("/profile", response_class=HTMLResponse)
def profile(request:Request,db:Session=Depends(get_db)): return member_page(request,"profile.html",db)


@app.post("/rewards/{reward_id}/redeem")
@limiter.limit("5/minute")
def redeem(request:Request,reward_id:int,csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    with db.begin_nested():
        reward=db.scalar(select(Reward).where(Reward.id==reward_id,Reward.active.is_(True)).with_for_update())
        locked=db.scalar(select(User).where(User.id==user.id).with_for_update())
        if not reward: raise HTTPException(404,"Reward unavailable")
        if locked.miles_balance < reward.miles_cost: raise HTTPException(400,"Not Enough Miles")
        if reward.quantity is not None and reward.quantity < 1: raise HTTPException(400,"Reward unavailable")
        before=locked.miles_balance; locked.miles_balance-=reward.miles_cost
        if reward.quantity is not None: reward.quantity-=1
        db.add(Transaction(user_id=locked.id,type="REWARD_REDEMPTION",description=reward.name,reference=f"REWARD-{reward.id}",miles_change=-reward.miles_cost,balance_before=before,balance_after=locked.miles_balance,created_by=locked.id)); db.add(Redemption(user_id=locked.id,reward_id=reward.id,miles_cost=reward.miles_cost))
    db.commit(); return RedirectResponse("/rewards?redeemed=1",303)


def require_staff(request,db):
    user=current_user(request,db)
    if permission(user,settings) not in {"STAFF","ADMIN","OWNER"}: raise HTTPException(403,"Access denied")
    return user


@app.get("/admin",response_class=HTMLResponse)
def admin(request:Request,q:str="",db:Session=Depends(get_db)):
    actor=require_staff(request,db); users=[]
    if q: users=db.scalars(select(User).where(or_(User.discord_display_name.ilike(f"%{q}%"),User.discord_username.ilike(f"%{q}%"),User.discord_user_id==q,User.roblox_username.ilike(f"%{q}%"),User.roblox_user_id==q,User.skymiles_number.ilike(f"%{q}%"))).limit(25)).all()
    return templates.TemplateResponse("admin.html",context(request,user=actor,users=users,auth=permission(actor,settings)))


@app.post("/admin/members/{user_id}/miles")
@limiter.limit("20/minute")
def adjust(request:Request,user_id:int,amount:int=Form(...),reason:str=Form(...),reference:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=require_staff(request,db)
    if not reason.strip() or amount==0 or abs(amount)>1_000_000: raise HTTPException(422,"A valid amount and reason are required")
    with db.begin_nested():
        target=db.scalar(select(User).where(User.id==user_id).with_for_update())
        if not target: raise HTTPException(404,"Member not found")
        before=target.miles_balance; target.miles_balance=max(0,before+amount); actual=target.miles_balance-before
        if actual>0: target.lifetime_miles+=actual
        db.add(Transaction(user_id=target.id,type="MILES_ADDED" if actual>0 else "MILES_DEDUCTED",description=reason.strip(),reference=reference[:100],miles_change=actual,balance_before=before,balance_after=target.miles_balance,created_by=actor.id)); db.add(AuditLog(staff_user_id=actor.id,target_user_id=target.id,action="MILES_ADDED" if actual>0 else "MILES_DEDUCTED",old_value={"balance":before},new_value={"balance":target.miles_balance},reason=reason.strip(),security_metadata={"ip":request.client.host if request.client else None}))
    db.commit(); return RedirectResponse(f"/admin?q={target.skymiles_number}",303)


@app.post("/logout")
def logout(request:Request,csrf:str=Form(...)):
    check_csrf(request,csrf); request.session.clear(); response=RedirectResponse("/",303); response.delete_cookie("skymiles_session"); return response


@app.get("/error",response_class=HTMLResponse)
def error(request:Request,kind:str="authentication"): return templates.TemplateResponse("error.html",context(request,title=f"{kind.title()} Verification Failed",message="We couldn't complete secure verification. Please try again."),status_code=400)


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    titles={401:"Session Expired",403:"Access Denied",404:"Page Not Found"}
    return templates.TemplateResponse("error.html",context(request,title=titles.get(exc.status_code,"Something Went Wrong"),message=str(exc.detail)),status_code=exc.status_code)


@app.exception_handler(Exception)
async def server_error(request, exc): return templates.TemplateResponse("error.html",context(request,title="Server Error",message="Our flight systems encountered turbulence. Please try again later."),status_code=500)
