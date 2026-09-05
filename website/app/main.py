import asyncio
import io
import re
import secrets
from time import time
from uuid import uuid4
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .discord_gateway import start_discord_gateway
from .models import AuditLog, Booking, Feedback, Flight, FlightStatus, ModerationAction, NotificationLog, Redemption, Reward, Status, Tier, TierConfig, Transaction, User, WebSession
from .oauth import discord_announce_booking, discord_announce_update, discord_authorize, discord_custom_emoji_assets, discord_custom_emojis, discord_dm, discord_guild_roles, discord_identity, discord_member_roles, discord_remove_skymiles_roles, discord_scheduled_events, discord_set_medallion_roles, discord_sync_skymiles_roles, expected_skymiles_role_ids, roblox_authorize, roblox_identity
from .security import check_csrf, consume_oauth, csrf_token, current_user, oauth_values, permission
from .session import DatabaseSessionMiddleware

ROOT = Path(__file__).resolve().parents[1]
# Any application, template, or stylesheet change creates a new release notice key.
ASSET_VERSION = str(int(max(
    path.stat().st_mtime
    for folder in (ROOT / "app", ROOT / "templates", ROOT / "static")
    for path in folder.rglob("*") if path.is_file()
)))
settings = get_settings()
templates = Jinja2Templates(directory=ROOT / "templates")
limiter = Limiter(key_func=get_remote_address)
FLIGHT_TERMINAL_GRACE = timedelta(minutes=10)


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
                db.add(TierConfig(tier=tier, miles_threshold=miles, mqp_threshold=mqp, segments_threshold=segments, description=description, benefits=benefits, enrollment_cost=miles))
            for name, desc, cost in [("Priority Boarding","Board first at a community flight.",2500),("Flight Upgrade","Upgrade an eligible roleplay itinerary.",5000),("Exclusive Discord Role","Unlock a distinguished community role.",10000),("Special Aircraft Access","Access a featured community aircraft.",15000)]: db.add(Reward(name=name, description=desc, miles_cost=cost, active=True))
            db.commit()
    await expire_medallions_once()
    expiration_task = asyncio.create_task(medallion_expiration_worker())
    reminder_task = asyncio.create_task(flight_reminder_worker())
    discord_gateway = await start_discord_gateway(settings)
    try:
        yield
    finally:
        expiration_task.cancel()
        reminder_task.cancel()
        if discord_gateway:
            await discord_gateway.close()


app = FastAPI(title="Delta SkyMiles | Roblox", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda r, e: JSONResponse({"detail":"Too many requests"}, 429))
app.add_middleware(DatabaseSessionMiddleware, secure=settings.cookie_secure, max_age=86400)
app.add_middleware(GZipMiddleware, minimum_size=800)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def cache_static_assets(request: Request, call_next):
    """Cache deployment assets and avoid retransmitting large CSS/SVG files."""
    response=await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"]="public, max-age=3600, stale-while-revalidate=86400"
    return response


def context(request, **values):
    user=values.get("user")
    show_feedback=False
    if user and not request.session.get("feedback_prompted") and secrets.randbelow(4)==0:
        request.session["feedback_prompted"]=True; show_feedback=True
    discord_roles=[]; discord_role_details=[]
    role_sync_state=getattr(user,"_discord_sync_state","unavailable") if user else "unavailable"
    if user:
        discord_role_details=getattr(user,"_discord_role_details",[])
        if not discord_role_details:
            role_names={settings.discord_member_role_id:"SkyMiles Member"}
            role_names.update({role_id:f"{tier.title()} Medallion" for tier,role_id in settings.medallion_role_ids.items() if role_id})
            role_names.update({role_id:"Ownership" for role_id in settings.ids(settings.owner_discord_role_ids)})
            role_names.update({role_id:"Staff Admin" for role_id in settings.ids(settings.admin_discord_role_ids)})
            role_names.update({role_id:"Staff" for role_id in settings.ids(settings.staff_discord_role_ids)})
            discord_role_details=[{"id":role_id,"name":role_names[role_id],"color":0} for role_id in user.discord_role_ids or [] if role_id in role_names]
        discord_roles=[role["name"] for role in discord_role_details]
    return {"request":request,"csrf":csrf_token(request),"settings":settings,"asset_version":ASSET_VERSION,"show_feedback":show_feedback,"discord_roles":discord_roles,"discord_role_details":discord_role_details,"role_sync_state":role_sync_state,**values}


def qualifies_for_tier(user: User, tier: TierConfig) -> bool:
    """Require every published qualification for Medallion enrollment."""
    return (
        user.lifetime_miles >= tier.miles_threshold
        and user.medallion_qualifying_points >= tier.mqp_threshold
        and user.segments_flown >= tier.segments_threshold
    )


TIER_ORDER = {Tier.MEMBER: 0, Tier.SILVER: 1, Tier.GOLD: 2, Tier.PLATINUM: 3, Tier.DIAMOND: 4}


def is_tier_upgrade(current: Tier, desired: Tier) -> bool:
    """Members may move upward during a status year, but never sideways or down."""
    return TIER_ORDER[desired] > TIER_ORDER[current]


def display_discord_roles(member_role_ids: list[str], catalog: list[dict]) -> list[dict]:
    """Map authoritative member role IDs to display-safe guild role metadata."""
    member_ids=set(member_role_ids or [])
    return [{"id":str(role["id"]),"name":str(role["name"]),"color":int(role.get("color",0))} for role in catalog if str(role["id"]) in member_ids and role.get("name")!="@everyone"]


def assigned(value) -> str: return str(value) if value not in {None,""} else "To Be Assigned"


def confirmation_number() -> str: return "DL"+secrets.token_hex(5).upper()


def validated_roblox_game_url(value:str) -> str:
    """Accept only HTTPS Roblox links; never encode an arbitrary site in a boarding QR."""
    parsed=urlparse(value.strip())
    hostname=(parsed.hostname or "").lower()
    if parsed.scheme!="https" or parsed.username or parsed.password or not (hostname=="roblox.com" or hostname.endswith(".roblox.com")):
        raise ValueError("Enter a valid https://www.roblox.com game or share link")
    return value.strip()


def release_expired_restriction(user:User,db:Session) -> None:
    if user.account_status!=Status.ACTIVE and not user.permanent_ban and user.restricted_until and user.restricted_until<=datetime.now(timezone.utc):
        user.account_status=Status.ACTIVE; user.restricted_until=None; user.restriction_reason=None; db.commit()


async def notify_member(db:Session,user:User,flight:Flight|None,booking:Booking|None,kind:str,content:str,event_key:str):
    """Deliver at most one event notification and always retain its outcome."""
    log=NotificationLog(user_id=user.id,flight_id=flight.id if flight else None,booking_id=booking.id if booking else None,notification_type=kind,event_key=event_key,delivery_status="PENDING",error=None)
    try: db.add(log); db.commit()
    except IntegrityError: db.rollback(); return
    try: await discord_dm(settings,user.discord_user_id,content)
    except Exception as exc: log.delivery_status="FAILED"; log.error=str(exc)[:1000]
    else: log.delivery_status="DELIVERED"
    db.commit()


async def emoji_map() -> dict[str,str]:
    try: return await discord_custom_emojis(settings)
    except Exception: return {}


def em(emojis:dict,name:str,fallback:str) -> str:
    return emojis.get(name.lower(),fallback)


@app.get("/health")
def health(): return JSONResponse({"status":"ok"},headers={"Cache-Control":"no-store"})


@app.get("/api/discord-emojis")
async def web_discord_emojis(request:Request,db:Session=Depends(get_db)):
    current_user(request,db)
    try: return JSONResponse(await discord_custom_emoji_assets(settings),headers={"Cache-Control":"private, max-age=300"})
    except Exception: return JSONResponse({})


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
        release_expired_restriction(existing,db)
        existing.roblox_username, existing.roblox_display_name, existing.roblox_avatar_url = identity["username"], identity["display_name"], identity["avatar"]
        existing.roblox_group_role, existing.roblox_group_rank = role.get("name"), int(role.get("rank",0)); db.commit()
        request.session["link_user_id"] = existing.id
        if existing.discord_verified_at and existing.account_status == Status.ACTIVE:
            request.session.clear(); request.session["user_id"]=existing.id; request.session["authorization"]=permission(existing,settings); request.session["theme"]=existing.theme_preference
            return RedirectResponse("/dashboard",303)
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


@app.get("/auth/discord/login")
@limiter.limit("10/minute")
def start_discord_login(request: Request):
    if not settings.discord_client_id or not settings.discord_guild_id: raise HTTPException(503,"Discord OAuth is not configured")
    request.session["discord_login_only"]=True
    state, challenge = oauth_values(request, "discord")
    return RedirectResponse(discord_authorize(settings, state, challenge))


def next_number(db):
    last = db.scalar(select(User.skymiles_number).order_by(User.id.desc()).limit(1))
    return f"SM-{(int(last.split('-')[1]) + 1 if last else 1):08d}"


@app.get("/auth/discord/callback")
@limiter.limit("10/minute")
async def discord_callback(request: Request, code: str, state: str, db: Session=Depends(get_db)):
    pending = request.session.get("pending_roblox")
    direct_login = bool(request.session.pop("discord_login_only",False))
    if not pending and not direct_login: raise HTTPException(401, "Verification session expired")
    verifier = consume_oauth(request, "discord", state)
    try: identity = await discord_identity(settings, code, verifier)
    except Exception: return RedirectResponse("/error?kind=discord",303)
    if not identity["member"]: return templates.TemplateResponse("restricted.html", context(request, kind="discord"), status_code=403)
    if direct_login:
        user=db.scalar(select(User).where(User.discord_user_id==identity["id"]))
        if not user: return templates.TemplateResponse("error.html",context(request,title="Roblox Verification Required",message="Verify with Roblox first to create your SkyMiles membership."),status_code=404)
        release_expired_restriction(user,db)
        if user.account_status != Status.ACTIVE: raise HTTPException(403,"Account suspended")
        user.discord_username=identity["username"]; user.discord_display_name=identity["display_name"]; user.discord_avatar_url=identity["avatar"]; user.discord_role_ids=identity["member"].get("roles",[]); user.discord_verified_at=datetime.now(timezone.utc)
        try: user.discord_role_ids=await discord_sync_skymiles_roles(settings,user.discord_user_id,user.tier.name if user.tier!=Tier.MEMBER else None)
        except Exception: pass
        db.commit()
        request.session.clear(); request.session["user_id"]=user.id; request.session["authorization"]=permission(user,settings); request.session["theme"]=user.theme_preference
        return RedirectResponse("/dashboard",303)
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
    db.refresh(user)
    try:
        user.discord_role_ids=await discord_sync_skymiles_roles(settings,user.discord_user_id,user.tier.name if user.tier!=Tier.MEMBER else None); db.commit()
    except Exception: pass  # Account creation must survive a temporary Discord role outage.
    request.session.clear(); request.session["user_id"]=user.id; request.session["authorization"]=permission(user,settings); request.session["theme"]=user.theme_preference
    return RedirectResponse("/dashboard",303)


async def refresh_discord_authorization(user: User, db: Session) -> str:
    if settings.discord_bot_token:
        roles=None
        try:
            tier_name=user.tier.name if user.tier!=Tier.MEMBER else None
            roles=await discord_member_roles(settings,user.discord_user_id)
            if roles is None: raise RuntimeError("Discord roles could not be read")
            actual=set(roles); expected=expected_skymiles_role_ids(settings,tier_name); managed={settings.discord_member_role_id,*settings.medallion_role_ids.values()}-{""}
            user.discord_role_ids=roles if expected.issubset(actual) and not actual & (managed-expected) else await discord_sync_skymiles_roles(settings,user.discord_user_id,tier_name)
            user._discord_sync_state="synced"; db.commit()
        except Exception:
            if roles is not None:
                user.discord_role_ids=roles; db.commit()  # Discord answered authoritatively even if managed-role repair failed.
            user._discord_sync_state="error"  # Retain cache only when Discord itself is unreachable.
    else: user._discord_sync_state="unavailable"
    try:
        catalog=await discord_guild_roles(settings)
        member_role_ids=set(user.discord_role_ids or [])
        user._discord_role_details=display_discord_roles(list(member_role_ids),catalog)
    except Exception: user._discord_role_details=[]
    return permission(user,settings)


async def member_page(request: Request, template: str, db: Session):
    user=current_user(request,db)
    last_sync=float(request.session.get("discord_sync_checked_at",0) or 0)
    if time()-last_sync<30:
        user._discord_sync_state="synced"
        try: user._discord_role_details=display_discord_roles(user.discord_role_ids or [],await discord_guild_roles(settings))
        except Exception: user._discord_role_details=[]
        auth=permission(user,settings)
    else:
        auth=await refresh_discord_authorization(user,db); request.session["discord_sync_checked_at"]=time()
    transactions=db.scalars(select(Transaction).where(Transaction.user_id==user.id).order_by(Transaction.created_at.desc()).limit(20)).all() if template in {"dashboard.html","activity.html"} else []
    rewards=db.scalars(select(Reward).where(Reward.active.is_(True))).all() if template=="rewards.html" else []
    tiers=db.scalars(select(TierConfig).order_by(TierConfig.miles_threshold)).all() if template=="miles.html" else []
    return templates.TemplateResponse(template, context(request,user=user,transactions=transactions,rewards=rewards,tiers=tiers,auth=auth))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request:Request,db:Session=Depends(get_db)): return await member_page(request,"dashboard.html",db)
@app.get("/miles", response_class=HTMLResponse)
async def miles(request:Request,db:Session=Depends(get_db)): return await member_page(request,"miles.html",db)
@app.get("/activity", response_class=HTMLResponse)
async def activity(request:Request,db:Session=Depends(get_db)): return await member_page(request,"activity.html",db)
@app.get("/rewards", response_class=HTMLResponse)
async def rewards(request:Request,db:Session=Depends(get_db)): return await member_page(request,"rewards.html",db)
@app.get("/profile", response_class=HTMLResponse)
async def profile(request:Request,db:Session=Depends(get_db)): return await member_page(request,"profile.html",db)


@app.get("/trips",response_class=HTMLResponse)
async def my_trips(request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db); auth=await refresh_discord_authorization(user,db)
    trips=db.execute(select(Booking,Flight).join(Flight,Booking.flight_id==Flight.id).where(Booking.user_id==user.id).order_by(Flight.starts_at.desc())).all()
    return templates.TemplateResponse("trips.html",context(request,user=user,trips=trips,auth=auth,now=datetime.now(timezone.utc)))


@app.get("/trips/{confirmation}",response_class=HTMLResponse)
async def trip_detail(request:Request,confirmation:str,db:Session=Depends(get_db)):
    user=current_user(request,db); auth=await refresh_discord_authorization(user,db)
    row=db.execute(select(Booking,Flight).join(Flight,Booking.flight_id==Flight.id).where(Booking.user_id==user.id,Booking.confirmation_number==confirmation)).first()
    if not row: raise HTTPException(404,"Trip not found")
    booking,flight=row; refund_until=booking.created_at+timedelta(hours=24); refund_eligible=datetime.now(timezone.utc)<=refund_until and booking.status=="CONFIRMED"
    catalog={item["id"]:item for item in eligible_amenities(user)}
    boarding_time=flight.starts_at-timedelta(minutes=30)
    zone={"Delta One":"1","First Class":"2","Delta Comfort":"3","Delta Main":"5"}.get(booking.cabin,"To Be Assigned")
    return templates.TemplateResponse("trip_detail.html",context(request,user=user,booking=booking,flight=flight,refund_until=refund_until,refund_eligible=refund_eligible,amenity_catalog=catalog,boarding_time=boarding_time,zone=zone,auth=auth))


@app.get("/trips/{confirmation}/qr.svg")
async def trip_game_qr(request:Request,confirmation:str,db:Session=Depends(get_db)):
    """Generate a private booking QR that resolves only to the staff-approved Roblox URL."""
    user=current_user(request,db)
    row=db.execute(select(Booking,Flight).join(Flight,Booking.flight_id==Flight.id).where(Booking.user_id==user.id,Booking.confirmation_number==confirmation)).first()
    if not row: raise HTTPException(404,"Trip not found")
    _,flight=row
    if not flight.roblox_game_url: raise HTTPException(404,"The Roblox game link has not been assigned")
    try:
        import qrcode
        import qrcode.image.svg
        image=qrcode.make(flight.roblox_game_url,image_factory=qrcode.image.svg.SvgPathImage,box_size=8,border=3)
        output=io.BytesIO(); image.save(output)
    except Exception as exc: raise HTTPException(503,"The boarding QR code is temporarily unavailable") from exc
    return Response(output.getvalue(),media_type="image/svg+xml",headers={"Cache-Control":"private, max-age=300","Content-Disposition":f'inline; filename="{confirmation}-boarding-qr.svg"'})


@app.get("/settings", response_class=HTMLResponse)
async def account_settings(request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    auth=await refresh_discord_authorization(user,db)
    return templates.TemplateResponse("settings.html",context(request,user=user,theme=request.session.get("theme","light"),auth=auth))


@app.post("/settings/theme")
def update_theme(request:Request,theme:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    if theme not in {"light","dark","system"}: raise HTTPException(422,"Invalid theme")
    request.session["theme"]=theme; user.theme_preference=theme; db.commit()
    return RedirectResponse("/settings?theme_saved=1",303)


@app.post("/feedback")
@limiter.limit("3/day")
def submit_feedback(request:Request,website_rating:int=Form(...),community_rating:int=Form(...),message:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    if website_rating not in range(1,6) or community_rating not in range(1,6): raise HTTPException(422,"Ratings must be between 1 and 5 stars")
    clean=message.strip()
    if len(clean)<10 or len(clean)>1500: raise HTTPException(422,"Feedback must be between 10 and 1,500 characters")
    db.add(Feedback(user_id=user.id,website_rating=website_rating,community_rating=community_rating,message=clean)); db.commit()
    request.session["feedback_submitted"]=True
    return RedirectResponse("/dashboard?feedback_received=1",303)


@app.post("/settings/quit")
@limiter.limit("2/hour")
async def quit_skymiles(request:Request,confirmation:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    if confirmation.strip().upper() != "QUIT": raise HTTPException(422,"Type QUIT to confirm")
    old_balance=user.miles_balance; old_tier=user.tier.value
    if old_balance:
        db.add(Transaction(user_id=user.id,type="MEMBERSHIP_ENDED",description="SkyMiles forfeited when membership ended",reference="MEMBERSHIP-QUIT",miles_change=-old_balance,balance_before=old_balance,balance_after=0,created_by=user.id))
    user.miles_balance=0; user.lifetime_miles=0; user.medallion_qualifying_points=0; user.segments_flown=0
    user.tier=Tier.MEMBER; user.medallion_expires_at=None; user.account_status=Status.DISABLED
    db.add(AuditLog(staff_user_id=user.id,target_user_id=user.id,action="MEMBERSHIP_ENDED",old_value={"status":"ACTIVE","tier":old_tier,"miles_balance":old_balance},new_value={"status":"DISABLED","tier":Tier.MEMBER.value,"miles_balance":0},reason="Member voluntarily left the SkyMiles program",security_metadata={"ip":request.client.host if request.client else None,"self_service":True}))
    try:
        if not await discord_remove_skymiles_roles(settings,user.discord_user_id): raise HTTPException(503,"Discord role synchronization is not configured")
    except HTTPException: db.rollback(); raise
    except Exception as exc: db.rollback(); raise HTTPException(502,"Could not remove the Discord roles; your membership was not changed") from exc
    db.commit()
    request.session.clear()
    response=RedirectResponse("/?membership_ended=1",303); response.delete_cookie("skymiles_session"); return response


@app.get("/medallions/{tier_name}", response_class=HTMLResponse)
async def medallion_detail(request:Request,tier_name:str,db:Session=Depends(get_db)):
    user=current_user(request,db)
    auth=await refresh_discord_authorization(user,db)
    try: desired=Tier[tier_name.upper()]
    except KeyError: raise HTTPException(404,"Medallion tier not found")
    if desired == Tier.MEMBER: raise HTTPException(404,"Medallion tier not found")
    tier=db.scalar(select(TierConfig).where(TierConfig.tier==desired))
    if not tier: raise HTTPException(404,"Medallion tier not found")
    qualifies=qualifies_for_tier(user,tier)
    return templates.TemplateResponse("medallion_detail.html",context(request,user=user,tier=tier,qualifies=qualifies,can_upgrade=is_tier_upgrade(user.tier,desired),auth=auth))


def eligible_amenities(user: User) -> list[dict]:
    amenities = [{"id":"wifi","name":"Wi-Fi","emoji":"WiFi","description":"Connectivity when offered on the assigned aircraft."},{"id":"personal_screen","name":"Personal Entertainment Screen","emoji":"PersonalScreen","description":"Seatback entertainment when available."},{"id":"in_seat_power","name":"In-Seat Power","emoji":"InSeatPower","description":"Power at the assigned seat."},{"id":"usb_power","name":"USB Power","emoji":"USBPower","description":"USB charging at the assigned seat."},{"id":"snacks","name":"Snacks","emoji":"Snacks","description":"Complimentary roleplay snack service."}]
    if user.tier in {Tier.GOLD, Tier.PLATINUM, Tier.DIAMOND}: amenities += [{"id":"satellite_tv","name":"Satellite TV","emoji":"Satelite","description":"Live television when available."},{"id":"meal","name":"Meal","emoji":"food","description":"Meal service for this itinerary."}]
    if user.tier in {Tier.PLATINUM, Tier.DIAMOND}: amenities.append({"id":"lie_flat_bed","name":"Lie-Flat Bed","emoji":"Bed","description":"Lie-flat seating when assigned."})
    return amenities


def next_medallion_expiration(now: datetime | None = None) -> datetime:
    """Return next January 1 at midnight Eastern, stored as UTC."""
    eastern = ZoneInfo("America/New_York")
    current = (now or datetime.now(timezone.utc)).astimezone(eastern)
    return datetime(current.year + 1, 1, 1, 0, 0, tzinfo=eastern).astimezone(timezone.utc)


async def expire_medallions_once() -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        expired = db.scalars(select(User).where(User.tier != Tier.MEMBER, User.medallion_expires_at.is_not(None), User.medallion_expires_at <= now)).all()
        for user in expired:
            old_tier = user.tier.value
            user.tier = Tier.MEMBER
            user.medallion_expires_at = None
            db.add(AuditLog(staff_user_id=user.id,target_user_id=user.id,action="MEDALLION_EXPIRED",old_value={"tier":old_tier},new_value={"tier":Tier.MEMBER.value},reason="Annual Medallion term ended at midnight Eastern on January 1",security_metadata={"automatic":True}))
        db.commit()
        identities = [(user.discord_user_id, user.id) for user in expired]
    for discord_user_id, _ in identities:
        try: await discord_set_medallion_roles(settings, discord_user_id, None)
        except Exception: pass
    return len(identities)


async def medallion_expiration_worker():
    while True:
        await asyncio.sleep(3600)
        await expire_medallions_once()


async def flight_reminder_worker():
    """Notify confirmed passengers once when departure enters the next 24 hours."""
    while True:
        now=datetime.now(timezone.utc)
        with SessionLocal() as db:
            rows=db.execute(select(Booking,Flight,User).join(Flight,Booking.flight_id==Flight.id).join(User,Booking.user_id==User.id).where(Booking.status=="CONFIRMED",Flight.status.in_([FlightStatus.SCHEDULED,FlightStatus.DELAYED]),Flight.starts_at>now,Flight.starts_at<=now+timedelta(hours=24))).all()
            emojis=await emoji_map()
            for booking,flight,user in rows:
                content=f"{em(emojis,'Timer','⏱️')} Delta Air Lines | Flight Reminder\n\nYour upcoming flight is approaching.\n\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'Schedule','📅')} Departure: {flight.starts_at.strftime('%b %d, %Y at %H:%M UTC')}\n{em(emojis,'Parking','🅿️')} Gate: {assigned(flight.gate)}\n{em(emojis,'Nametag','🏷️')} Seat: {assigned(booking.seat)}\n{em(emojis,{'Delta Main':'DeltaMain','Delta Comfort':'Comfort','First Class':'FirstClass','Delta One':'DeltaOne'}.get(booking.cabin,'DeltaMain'),'💺')} Cabin: {assigned(booking.cabin)}\n\nPlease be ready before the scheduled departure time.\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
                await notify_member(db,user,flight,booking,"FLIGHT_REMINDER",content,f"booking:{booking.id}:reminder:24h")
        await asyncio.sleep(900)


async def sync_flights(db: Session) -> int:
    events = await discord_scheduled_events(settings)
    for event in events:
        if not event.get("scheduled_start_time"): continue
        flight = db.scalar(select(Flight).where(Flight.discord_event_id == str(event["id"])))
        if not flight:
            flight = Flight(discord_event_id=str(event["id"]), name=event["name"], starts_at=datetime.fromisoformat(event["scheduled_start_time"].replace("Z","+00:00")))
            db.add(flight)
        flight.name = event["name"]
        flight.description = event.get("description") or "Community flight"
        flight.location = (event.get("entity_metadata") or {}).get("location") or "Delta Roblox Community"
        flight.starts_at = datetime.fromisoformat(event["scheduled_start_time"].replace("Z","+00:00"))
        flight.ends_at = datetime.fromisoformat(event["scheduled_end_time"].replace("Z","+00:00")) if event.get("scheduled_end_time") else None
        flight.image_url = f"https://cdn.discordapp.com/guild-events/{event['id']}/{event['image']}.png" if event.get("image") else None
        if event.get("status") == 4: flight.status = FlightStatus.COMPLETED
    db.commit()
    return len(events)


@app.get("/flights", response_class=HTMLResponse)
async def flights(request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    auth=await refresh_discord_authorization(user,db)
    try: await sync_flights(db)
    except Exception: pass
    terminal_cutoff=datetime.now(timezone.utc)-FLIGHT_TERMINAL_GRACE
    available=db.scalars(select(Flight).where(or_(Flight.status.in_([FlightStatus.SCHEDULED,FlightStatus.DELAYED]),Flight.updated_at>terminal_cutoff)).order_by(Flight.starts_at)).all()
    member_bookings=db.scalars(select(Booking).where(Booking.user_id==user.id)).all()
    bookings={booking.flight_id:booking for booking in member_bookings}
    return templates.TemplateResponse("flights.html",context(request,user=user,flights=available,bookings=bookings,amenities=eligible_amenities(user),auth=auth))


@app.post("/flights/{flight_id}/book")
@limiter.limit("10/minute")
async def book_flight(request:Request,flight_id:int,csrf:str=Form(...),amenities:list[str]=Form(default=[]),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    if user.account_status!=Status.ACTIVE or user.permanent_ban or (user.restricted_until and user.restricted_until>datetime.now(timezone.utc)): raise HTTPException(403,"Your SkyMiles account is restricted")
    flight=db.get(Flight,flight_id)
    if not flight or flight.status in {FlightStatus.CANCELLED,FlightStatus.COMPLETED}: raise HTTPException(400,"This flight is not available for booking")
    allowed={item["id"] for item in eligible_amenities(user)}
    selected=[item for item in amenities if item in allowed]
    existing=db.scalar(select(Booking).where(Booking.flight_id==flight.id,Booking.user_id==user.id))
    cabin={Tier.DIAMOND:"Delta One",Tier.PLATINUM:"First Class",Tier.GOLD:"Delta Comfort"}.get(user.tier,"Delta Main")
    if existing:
        if existing.status!="CONFIRMED": existing.created_at=datetime.now(timezone.utc); existing.miles_refunded=0
        existing.amenities=selected; existing.status="CONFIRMED"; existing.cancelled_at=None
    else:
        existing=Booking(flight_id=flight.id,user_id=user.id,amenities=selected,confirmation_number=confirmation_number(),cabin=cabin,carry_on="1 Carry-On",checked_bags="To Be Assigned",miles_used=0)
        db.add(existing)
    db.commit()
    try:
        await discord_announce_booking(settings,discord_user_id=user.discord_user_id,display_name=user.discord_display_name,flight_number=flight.flight_number or flight.name,route=f"{flight.departure_airport or 'TBA'} → {flight.destination_airport or 'TBA'}")
    except Exception:
        pass  # A Discord outage must not undo a confirmed booking.
    emojis=await emoji_map(); depart=flight.starts_at.strftime("%b %d, %Y at %H:%M UTC"); arrival=flight.ends_at.strftime("%b %d, %Y at %H:%M UTC") if flight.ends_at else "To Be Assigned"
    cabin_emoji={"Delta Main":"DeltaMain","Delta Comfort":"Comfort","First Class":"FirstClass","Delta One":"DeltaOne"}.get(existing.cabin,"DeltaMain")
    content=f"{em(emojis,'CheckMark','✅')} Delta Air Lines | Booking Confirmed\n\nYour Delta Air Lines reservation has been confirmed.\n\n{em(emojis,'Ticket','🎟️')} Confirmation Number: {existing.confirmation_number}\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'Schedule','📅')} Departure: {depart}\n{em(emojis,'Schedule','📅')} Arrival: {arrival}\n{em(emojis,'Plane','✈️')} Aircraft: {assigned(flight.aircraft)}\n{em(emojis,'Parking','🅿️')} Gate: {assigned(flight.gate)}\n{em(emojis,cabin_emoji,'💺')} Cabin: {assigned(existing.cabin)}\n{em(emojis,'CreditCard','💳')} SkyMiles Used: {existing.miles_used:,}\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
    await notify_member(db,user,flight,existing,"BOOKING_CONFIRMED",content,f"booking:{existing.id}:confirmed:{existing.created_at.isoformat()}")
    return RedirectResponse(f"/trips/{existing.confirmation_number}?booked=1",303)


@app.post("/flights/{flight_id}/cancel")
@limiter.limit("10/minute")
async def cancel_booking(request:Request,flight_id:int,csrf:str=Form(...),db:Session=Depends(get_db)):
    """Release a reservation and every flight-only amenity before departure."""
    check_csrf(request,csrf); user=current_user(request,db)
    flight=db.get(Flight,flight_id)
    booking=db.scalar(select(Booking).where(Booking.flight_id==flight_id,Booking.user_id==user.id).with_for_update())
    if not flight or not booking or booking.status!="CONFIRMED": raise HTTPException(404,"Active booking not found")
    if flight.starts_at<=datetime.now(timezone.utc): raise HTTPException(409,"This flight has already departed and can no longer be cancelled")
    eligible=datetime.now(timezone.utc)<=booking.created_at+timedelta(hours=24)
    refunded=booking.miles_used if eligible else 0; forfeited=booking.miles_used-refunded
    if refunded: user.miles_balance+=refunded
    booking.status="CANCELLED"; booking.amenities=[]; booking.cancelled_at=datetime.now(timezone.utc); booking.miles_refunded=refunded; db.commit()
    try: await discord_announce_update(settings,title="Flight Booking Cancelled",description=f"{user.discord_display_name} left {flight.flight_number}. Their flight-only amenities were returned.")
    except Exception: pass
    emojis=await emoji_map(); content=f"{em(emojis,'CheckMark','✅')} Delta Air Lines | Cancellation Confirmed\n\nYour reservation has been cancelled successfully.\n\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'Ticket','🎟️')} Confirmation Number: {booking.confirmation_number}\n{em(emojis,'Schedule','📅')} Original Departure: {flight.starts_at.strftime('%b %d, %Y at %H:%M UTC')}\n\n{em(emojis,'CreditCard','💳')} SkyMiles Refunded: {refunded:,}\n{em(emojis,'Warning','⚠️')} SkyMiles Forfeited: {forfeited:,}\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
    await notify_member(db,user,flight,booking,"CANCELLATION_CONFIRMED",content,f"booking:{booking.id}:cancelled")
    if refunded:
        refund_content=f"{em(emojis,'CreditCard','💳')} Delta Air Lines | Refund Confirmed\n\nYour SkyMiles refund has been processed.\n\n{em(emojis,'Ticket','🎟️')} Confirmation Number: {booking.confirmation_number}\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'CreditCard','💳')} SkyMiles Refunded: {refunded:,}\n{em(emojis,'CreditCard','💳')} Updated Balance: {user.miles_balance:,}\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
        await notify_member(db,user,flight,booking,"REFUND_CONFIRMED",refund_content,f"booking:{booking.id}:refund:{booking.cancelled_at.isoformat()}")
    return RedirectResponse(f"/trips/{booking.confirmation_number}?cancelled=1",303)


@app.post("/tiers/{tier_name}/join")
@limiter.limit("5/minute")
async def join_tier(request:Request,tier_name:str,csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    try: desired=Tier[tier_name.upper()]
    except KeyError: raise HTTPException(404,"Medallion tier not found")
    with db.begin_nested():
        user=db.scalar(select(User).where(User.id==user.id).with_for_update())
        config=db.scalar(select(TierConfig).where(TierConfig.tier==desired))
        if not is_tier_upgrade(user.tier,desired): raise HTTPException(409,"You can only upgrade to a higher Medallion level during the current status year")
        if not config or not qualifies_for_tier(user,config): raise HTTPException(403,"You must meet the SkyMiles, MQP, and segment requirements for this Medallion level")
        if user.miles_balance < config.enrollment_cost: raise HTTPException(400,"Not Enough Miles")
        before=user.miles_balance; user.miles_balance-=config.enrollment_cost
        user.tier=desired; user.medallion_expires_at=next_medallion_expiration()
        db.add(Transaction(user_id=user.id,type="MEDALLION_ENROLLMENT",description=f"Joined {desired.value}",reference=desired.name,miles_change=-config.enrollment_cost,balance_before=before,balance_after=user.miles_balance,created_by=user.id))
    try:
        if not await discord_set_medallion_roles(settings,user.discord_user_id,desired.name): raise HTTPException(503,"Discord role synchronization is not configured")
    except HTTPException: db.rollback(); raise
    except Exception as exc: db.rollback(); raise HTTPException(502,"Could not assign the exact Discord Medallion role; no miles were spent") from exc
    db.commit()
    return RedirectResponse(f"/medallions/{desired.name}?joined=1",303)


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


async def require_staff(request,db):
    user=current_user(request,db)
    auth=await refresh_discord_authorization(user,db)
    if auth not in {"STAFF","ADMIN","OWNER"}: raise HTTPException(403,"Access denied")
    return user


async def require_admin(request,db):
    user=await require_staff(request,db)
    if permission(user,settings) not in {"ADMIN","OWNER"}: raise HTTPException(403,"Staff Admin access denied")
    return user


async def require_owner(request,db):
    user=await require_staff(request,db)
    if permission(user,settings) != "OWNER": raise HTTPException(403,"Ownership access denied")
    return user


def panel_path(auth: str) -> str:
    return "/owner" if auth=="OWNER" else "/admin" if auth=="ADMIN" else "/staff"


def persist_qualification_adjustment(db:Session,user_id:int,mqp:int,segments:int) -> tuple[User,dict,dict]:
    """Atomically persist qualification totals and verify the committed row."""
    target=db.scalar(select(User).where(User.id==user_id).with_for_update())
    if not target: raise HTTPException(404,"Member not found")
    before={"mqp":int(target.medallion_qualifying_points or 0),"segments":int(target.segments_flown or 0)}
    after={"mqp":before["mqp"]+mqp,"segments":before["segments"]+segments}
    result=db.execute(update(User).where(User.id==target.id).values(medallion_qualifying_points=after["mqp"],segments_flown=after["segments"]))
    if result.rowcount!=1: db.rollback(); raise HTTPException(409,"The qualification update could not be applied")
    db.flush(); db.refresh(target)
    if target.medallion_qualifying_points!=after["mqp"] or target.segments_flown!=after["segments"]: raise HTTPException(500,"Qualification verification failed")
    return target,before,after


async def render_staff_panel(request:Request,q:str,db:Session,required:str):
    actor=await ({"STAFF":require_staff,"ADMIN":require_admin,"OWNER":require_owner}[required])(request,db); users=[]
    if q: users=db.scalars(select(User).where(or_(User.discord_display_name.ilike(f"%{q}%"),User.discord_username.ilike(f"%{q}%"),User.discord_user_id==q,User.roblox_username.ilike(f"%{q}%"),User.roblox_user_id==q,User.skymiles_number.ilike(f"%{q}%"))).limit(25)).all()
    terminal_cutoff=datetime.now(timezone.utc)-FLIGHT_TERMINAL_GRACE
    flights=db.scalars(select(Flight).where(or_(Flight.status.in_([FlightStatus.SCHEDULED,FlightStatus.DELAYED]),Flight.updated_at>terminal_cutoff)).order_by(Flight.starts_at.desc()).limit(20)).all() if required in {"ADMIN","OWNER"} else []
    flight_logs=db.scalars(select(Flight).where(Flight.status.in_([FlightStatus.CANCELLED,FlightStatus.COMPLETED]),Flight.updated_at<=terminal_cutoff).order_by(Flight.updated_at.desc()).limit(100)).all() if required in {"ADMIN","OWNER"} else []
    feedback=db.execute(select(Feedback,User).join(User,Feedback.user_id==User.id).order_by(Feedback.created_at.desc()).limit(50)).all() if required=="OWNER" else []
    last_award=func.max(Transaction.created_at).label("last_award")
    member_directory=db.execute(select(User,last_award).outerjoin(Transaction,(Transaction.user_id==User.id) & (Transaction.miles_change>0)).where(User.account_status==Status.ACTIVE).group_by(User.id).order_by(last_award.desc().nullslast(),User.created_at.desc())).all()
    guild_roles=[]
    if required=="OWNER":
        try: guild_roles=await discord_guild_roles(settings)
        except Exception: pass
    audit_logs=db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)).all() if required=="OWNER" else []
    moderation_logs=db.scalars(select(ModerationAction).order_by(ModerationAction.created_at.desc()).limit(200)).all() if required=="OWNER" else []
    notification_logs=db.scalars(select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(200)).all() if required=="OWNER" else []
    directory_users=db.scalars(select(User)).all() if required=="OWNER" else []
    user_map={item.id:item for item in directory_users}
    member_bookings={member.id:db.execute(select(Booking,Flight).join(Flight,Booking.flight_id==Flight.id).where(Booking.user_id==member.id).order_by(Booking.created_at.desc()).limit(10)).all() for member in users}
    moderation={member.id:db.scalars(select(ModerationAction).where(ModerationAction.user_id==member.id).order_by(ModerationAction.created_at.desc()).limit(20)).all() for member in users}
    flight_form=request.session.pop("flight_form",{})
    flight_form_error=request.session.pop("flight_form_error",None)
    return templates.TemplateResponse("admin.html",context(request,user=actor,users=users,member_directory=member_directory,guild_roles=guild_roles,flights=flights,flight_logs=flight_logs,feedback=feedback,audit_logs=audit_logs,moderation_logs=moderation_logs,notification_logs=notification_logs,user_map=user_map,member_bookings=member_bookings,moderation=moderation,flight_form=flight_form,flight_form_error=flight_form_error,panel_level=required,auth=permission(actor,settings)))


@app.get("/staff",response_class=HTMLResponse)
async def staff_panel(request:Request,q:str="",db:Session=Depends(get_db)): return await render_staff_panel(request,q,db,"STAFF")


@app.get("/admin",response_class=HTMLResponse)
async def admin(request:Request,q:str="",db:Session=Depends(get_db)): return await render_staff_panel(request,q,db,"ADMIN")


@app.get("/owner",response_class=HTMLResponse)
async def owner_panel(request:Request,q:str="",db:Session=Depends(get_db)): return await render_staff_panel(request,q,db,"OWNER")


@app.post("/admin/members/{user_id}/miles")
@limiter.limit("20/minute")
async def adjust(request:Request,user_id:int,action:str=Form(...),amount:int=Form(...),reason:str=Form(...),reference:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=await require_staff(request,db)
    action=action.upper().strip()
    if action not in {"ADD","REMOVE"} or not reason.strip() or amount<=0 or amount>1_000_000: raise HTTPException(422,"Choose Add or Remove and enter a positive amount with a reason")
    signed_amount=amount if action=="ADD" else -amount
    with db.begin_nested():
        target=db.scalar(select(User).where(User.id==user_id).with_for_update())
        if not target: raise HTTPException(404,"Member not found")
        before=target.miles_balance; target.miles_balance=max(0,before+signed_amount); actual=target.miles_balance-before
        if actual>0: target.lifetime_miles+=actual
        db.add(Transaction(user_id=target.id,type="MILES_ADDED" if actual>0 else "MILES_DEDUCTED",description=reason.strip(),reference=reference[:100],miles_change=actual,balance_before=before,balance_after=target.miles_balance,created_by=actor.id)); db.add(AuditLog(staff_user_id=actor.id,target_user_id=target.id,action="MILES_ADDED" if actual>0 else "MILES_DEDUCTED",old_value={"balance":before},new_value={"balance":target.miles_balance},reason=reason.strip(),security_metadata={"ip":request.client.host if request.client else None}))
    db.commit()
    try: await discord_announce_update(settings,title="SkyMiles Adjustment",description=f"{actor.discord_display_name} adjusted {target.discord_display_name} by {actual:+,} SkyMiles.",fields=[{"name":"Reason","value":reason.strip()[:1024]},{"name":"New balance","value":f"{target.miles_balance:,}","inline":True}])
    except Exception: pass
    return RedirectResponse(f"{panel_path(permission(actor,settings))}?q={target.skymiles_number}&skymiles_applied=1",303)


@app.post("/admin/members/{user_id}/qualifications")
@limiter.limit("20/minute")
async def adjust_qualifications(request:Request,user_id:int,mqp:int=Form(0),segments:int=Form(0),reason:str=Form(...),reference:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=await require_staff(request,db)
    if not reason.strip() or mqp<0 or segments<0 or (mqp==0 and segments==0) or mqp>1_000_000 or segments>10_000:
        raise HTTPException(422,"Enter a positive MQP or segment amount and a reason")
    target,before,after=persist_qualification_adjustment(db,user_id,mqp,segments)
    db.add(AuditLog(staff_user_id=actor.id,target_user_id=target.id,action="QUALIFICATIONS_ADDED",old_value=before,new_value=after,reason=reason.strip(),security_metadata={"ip":request.client.host if request.client else None,"reference":reference[:100]})); db.commit(); db.refresh(target)
    try: await discord_announce_update(settings,title="Medallion Qualifications Added",description=f"{actor.discord_display_name} updated {target.discord_display_name}.",fields=[{"name":"MQP added","value":str(mqp),"inline":True},{"name":"Segments added","value":str(segments),"inline":True},{"name":"Reason","value":reason.strip()[:1024]}])
    except Exception: pass
    return RedirectResponse(f"{panel_path(permission(actor,settings))}?q={target.skymiles_number}&qualifications_applied=1&mqp_total={after['mqp']}&segments_total={after['segments']}",303)


@app.post("/admin/members/{user_id}/moderate")
@limiter.limit("10/minute")
async def moderate_member(request:Request,user_id:int,action:str=Form(...),reason:str=Form(...),flight_id:str=Form(""),moderation_id:str=Form(""),duration_hours:int=Form(0),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=await require_staff(request,db); level=permission(actor,settings)
    action=action.upper(); reason=reason.strip(); owner_actions={"REMOVE","SUSPEND","BAN_TEMPORARY","BAN_PERMANENT","RESTORE","REVERSE_WARNING"}
    if not reason or action not in {"WARN","NO_SHOW",*owner_actions}: raise HTTPException(422,"Choose a moderation action and enter a reason")
    if action in owner_actions and level!="OWNER": raise HTTPException(403,"Ownership access required")
    target=db.get(User,user_id); flight=db.get(Flight,int(flight_id)) if flight_id.isdigit() else None
    if not target: raise HTTPException(404,"Member not found")
    if action in {"WARN","NO_SHOW"} and not flight and action=="NO_SHOW": raise HTTPException(422,"A no-show must be linked to a flight")
    if action=="NO_SHOW":
        no_show_booking=db.scalar(select(Booking).where(Booking.user_id==target.id,Booking.flight_id==flight.id))
        if not no_show_booking: raise HTTPException(422,"No booking exists for that member and flight")
        no_show_booking.attendance_status="NO_SHOW"
    if action in {"SUSPEND","BAN_TEMPORARY"}:
        if duration_hours<1 or duration_hours>8760: raise HTTPException(422,"Restriction duration must be 1–8,760 hours")
        target.account_status=Status.SUSPENDED; target.restricted_until=datetime.now(timezone.utc)+timedelta(hours=duration_hours); target.restriction_reason=reason; target.permanent_ban=False
    elif action in {"BAN_PERMANENT","REMOVE"}:
        target.account_status=Status.DISABLED; target.permanent_ban=True; target.restricted_until=None; target.restriction_reason=reason
        if action=="REMOVE":
            before=target.miles_balance; target.miles_balance=0
            if before: db.add(Transaction(user_id=target.id,type="MEMBERSHIP_REMOVED",description=reason,reference="OWNERSHIP-REMOVAL",miles_change=-before,balance_before=before,balance_after=0,created_by=actor.id))
    elif action=="RESTORE": target.account_status=Status.ACTIVE; target.permanent_ban=False; target.restricted_until=None; target.restriction_reason=None
    elif action=="REVERSE_WARNING":
        previous=db.get(ModerationAction,int(moderation_id)) if moderation_id.isdigit() else None
        if not previous or previous.user_id!=target.id or previous.action not in {"WARN","NO_SHOW"} or previous.reversed_at: raise HTTPException(422,"Choose an active warning to reverse")
        previous.reversed_at=datetime.now(timezone.utc); previous.reversed_by=actor.id
    record=ModerationAction(user_id=target.id,moderator_id=actor.id,flight_id=flight.id if flight else None,action=action,reason=reason); db.add(record); db.flush()
    db.add(AuditLog(staff_user_id=actor.id,target_user_id=target.id,action=f"MODERATION_{action}",old_value=None,new_value={"restriction_until":target.restricted_until.isoformat() if target.restricted_until else None},reason=reason,security_metadata={"flight_id":flight.id if flight else None,"ip":request.client.host if request.client else None})); db.commit()
    emojis=await emoji_map(); count=db.scalar(select(func.count()).select_from(ModerationAction).where(ModerationAction.user_id==target.id,ModerationAction.action=="WARN",ModerationAction.reversed_at.is_(None))) or 0
    title="SkyMiles Warning" if action in {"WARN","NO_SHOW"} else "SkyMiles Account Banned" if action in {"BAN_PERMANENT","REMOVE"} else "SkyMiles Account Suspended" if action in {"SUSPEND","BAN_TEMPORARY"} else "SkyMiles Restriction Reversed"
    content=f"{em(emojis,'Warning','⚠️')} Delta Air Lines | {title}\n\n{em(emojis,'Warning','⚠️')} Reason: {reason}\n{em(emojis,'Plane','✈️')} Related Flight: {flight.flight_number if flight else 'Not Applicable'}\n{em(emojis,'Schedule','📅')} Issued: {datetime.now(timezone.utc).strftime('%b %d, %Y at %H:%M UTC')}\n{em(emojis,'Warning','⚠️')} Current Warning Count: {count}\n{em(emojis,'Timer','⏱️')} Restriction Ends: {target.restricted_until.strftime('%b %d, %Y at %H:%M UTC') if target.restricted_until else 'Permanent' if target.permanent_ban else 'Not Applicable'}\n\n{em(emojis,'Support','🛟')} Contact Delta Support if you believe this is incorrect.\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
    if action=="NO_SHOW":
        content=f"{em(emojis,'Warning','⚠️')} Delta Air Lines | Missed Flight\n\nOur verified records indicate that you did not attend your scheduled flight and did not cancel before departure.\n\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'Schedule','📅')} Departure: {flight.starts_at.strftime('%b %d, %Y at %H:%M UTC')}\n{em(emojis,'Ticket','🎟️')} Confirmation Number: {no_show_booking.confirmation_number}\n{em(emojis,'CreditCard','💳')} SkyMiles Forfeited: {no_show_booking.miles_used:,}\n{em(emojis,'Warning','⚠️')} Account Warning: {reason}\n\nIf you believe this is incorrect, contact Delta Support.\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
    await notify_member(db,target,flight,None,f"MODERATION_{action}",content,f"moderation:{record.id}")
    if action=="REMOVE":
        try: await discord_remove_skymiles_roles(settings,target.discord_user_id)
        except Exception: pass
    return RedirectResponse(f"{panel_path(level)}?q={target.skymiles_number}&moderation_applied=1",303)


@app.post("/owner/members/{user_id}/access")
@limiter.limit("10/minute")
async def owner_member_access(request:Request,user_id:int,action:str=Form(...),reason:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=await require_owner(request,db); action=action.upper().strip(); reason=reason.strip()
    if action not in {"KICK","BAN","RESTORE"} or not reason: raise HTTPException(422,"Choose an action and provide a reason")
    target=db.get(User,user_id)
    if not target: raise HTTPException(404,"Member not found")
    if target.id==actor.id or permission(target,settings)=="OWNER": raise HTTPException(403,"Ownership accounts cannot be changed here")
    old={"status":target.account_status.value}
    for session in db.scalars(select(WebSession)).all():
        if (session.data or {}).get("user_id")==target.id: db.delete(session)
    if action=="BAN": target.account_status=Status.DISABLED
    elif action=="RESTORE": target.account_status=Status.ACTIVE
    db.add(AuditLog(staff_user_id=actor.id,target_user_id=target.id,action=f"MEMBER_{action}",old_value=old,new_value={"status":target.account_status.value,"sessions_revoked":True},reason=reason,security_metadata={"ip":request.client.host if request.client else None}))
    if action=="BAN":
        try:
            if not await discord_remove_skymiles_roles(settings,target.discord_user_id): raise RuntimeError("Discord bot role synchronization is not configured")
        except Exception as exc: db.rollback(); raise HTTPException(502,"Discord roles could not be removed; the ban was not applied") from exc
    elif action=="RESTORE":
        try:
            if not await discord_set_medallion_roles(settings,target.discord_user_id,target.tier.name if target.tier!=Tier.MEMBER else None): raise RuntimeError("Discord bot role synchronization is not configured")
        except Exception as exc: db.rollback(); raise HTTPException(502,"Discord roles could not be restored; the account was not restored") from exc
    db.commit()
    try: await discord_announce_update(settings,title=f"Member {action.title()}",description=f"{actor.discord_display_name} applied **{action}** to {target.discord_display_name}.",fields=[{"name":"Reason","value":reason[:1024]}])
    except Exception: pass
    return RedirectResponse(f"/owner?q={target.skymiles_number}&access_updated=1",303)


@app.post("/admin/flights/sync")
async def admin_sync_flights(request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=await require_admin(request,db)
    await sync_flights(db)
    try: await discord_announce_update(settings,title="Discord Events Synchronized",description=f"{actor.discord_display_name} synchronized scheduled events with the website.")
    except Exception: pass
    return RedirectResponse(f"{panel_path(permission(actor,settings))}?flights_synced=1",303)


@app.post("/admin/flights/create")
async def admin_create_flight(request:Request,flight_number:str=Form(""),departure_airport:str=Form(""),destination_airport:str=Form(""),name:str=Form(""),starts_at:str=Form(""),ends_at:str=Form(""),aircraft:str=Form(""),gate:str=Form(""),roblox_game_url:str=Form(""),discord_event_url:str=Form(""),miles_reward:str=Form(""),description:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=await require_admin(request,db)
    submitted={"flight_number":flight_number,"departure_airport":departure_airport,"destination_airport":destination_airport,"name":name,"starts_at":starts_at,"ends_at":ends_at,"aircraft":aircraft,"gate":gate,"roblox_game_url":roblox_game_url,"discord_event_url":discord_event_url,"miles_reward":miles_reward,"description":description}
    def reject(message:str):
        request.session["flight_form"]=submitted; request.session["flight_form_error"]=message
        return RedirectResponse(panel_path(permission(actor,settings))+"#create-flight",303)
    number=" ".join(flight_number.upper().split()); departure=departure_airport.upper().strip(); destination=destination_airport.upper().strip()
    if not re.fullmatch(r"[A-Z]{2,4} ?\d{1,4}",number): return reject("Use a flight number such as DAL 1234.")
    if not re.fullmatch(r"[A-Z0-9]{3,4}",departure) or not re.fullmatch(r"[A-Z0-9]{3,4}",destination): return reject("Use valid 3–4 character airport codes.")
    if departure==destination: return reject("Departure and destination must be different.")
    try: reward=int(miles_reward)
    except (TypeError,ValueError): return reject("Enter a whole-number SkyMiles reward.")
    if reward < 0 or reward > 100_000: return reject("SkyMiles reward must be between 0 and 100,000.")
    try: game_url=validated_roblox_game_url(roblox_game_url)
    except ValueError as exc: return reject(str(exc)+". This link becomes the boarding-pass QR code.")
    event_id=None; event=None
    if discord_event_url.strip():
        match=re.fullmatch(r"https://discord\.com/events/(\d+)/(\d+)/?",discord_event_url.strip())
        if not match or match.group(1)!=settings.discord_guild_id: return reject("Use a scheduled-event link from the configured Discord server.")
        event_id=match.group(2)
        try: event=next((item for item in await discord_scheduled_events(settings) if str(item.get("id"))==event_id),None)
        except Exception: return reject("Discord could not be reached. Your entries were preserved; please try again.")
        if not event: return reject("Discord event not found. Your entries were preserved.")
        if db.scalar(select(Flight.id).where(Flight.discord_event_id==event_id)): return reject("That Discord event is already linked to a flight.")
    if event:
        departure_time=datetime.fromisoformat(event["scheduled_start_time"].replace("Z","+00:00")); arrival_time=datetime.fromisoformat(event["scheduled_end_time"].replace("Z","+00:00")) if event.get("scheduled_end_time") else None; name=(event.get("name") or name).strip(); description=(event.get("description") or description).strip(); location=(event.get("entity_metadata") or {}).get("location") or f"{departure} → {destination}"
    else:
        if not name.strip() or not starts_at: return reject("A title and departure time are required without a Discord event link.")
        try: departure_time=datetime.fromisoformat(starts_at).replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        except ValueError: return reject("Enter a valid departure date and time.")
        try: arrival_time=datetime.fromisoformat(ends_at).replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc) if ends_at else None
        except ValueError: return reject("Enter a valid arrival date and time.")
        if arrival_time and arrival_time<=departure_time: return reject("Arrival must be after departure.")
        location=f"{departure} → {destination}"
    flight=Flight(discord_event_id=event_id or f"manual-{uuid4().hex[:24]}",flight_number=number,departure_airport=departure,destination_airport=destination,name=name[:120],description=description[:1000],location=location,starts_at=departure_time,ends_at=arrival_time,aircraft=aircraft.strip()[:100] or None,gate=gate.strip()[:30] or None,roblox_game_url=game_url,miles_reward=reward,status=FlightStatus.SCHEDULED)
    db.add(flight); db.flush()
    db.add(AuditLog(staff_user_id=actor.id,target_user_id=None,action="FLIGHT_CREATED",old_value=None,new_value={"flight_id":flight.id,"number":number,"route":f"{departure}-{destination}","miles_reward":reward},reason="Staff-created community flight",security_metadata={"ip":request.client.host if request.client else None}))
    db.commit()
    try: await discord_announce_update(settings,title="Flight Created",description=f"{actor.discord_display_name} created {number}: {departure} → {destination}.",fields=[{"name":"SkyMiles reward","value":f"{reward:,}","inline":True},{"name":"Discord event","value":discord_event_url.strip() or "Manual flight"}])
    except Exception: pass
    return RedirectResponse(f"{panel_path(permission(actor,settings))}?flight_created=1",303)


@app.post("/admin/flights/{flight_id}/status")
async def admin_flight_status(request:Request,flight_id:int,status:str=Form(...),message:str=Form(""),gate:str=Form(""),aircraft:str=Form(""),starts_at:str=Form(""),ends_at:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=await require_admin(request,db)
    try: new_status=FlightStatus[status.upper()]
    except KeyError: raise HTTPException(422,"Invalid flight status")
    flight=db.get(Flight,flight_id)
    if not flight: raise HTTPException(404,"Flight not found")
    event_token=secrets.token_hex(6); old={"status":flight.status.value,"message":flight.status_message,"gate":flight.gate,"aircraft":flight.aircraft,"starts_at":flight.starts_at,"ends_at":flight.ends_at}
    flight.status=new_status; flight.status_message=message.strip()[:500] or None
    flight.gate=gate.strip()[:30] or flight.gate; flight.aircraft=aircraft.strip()[:100] or flight.aircraft
    try:
        if starts_at: flight.starts_at=datetime.fromisoformat(starts_at).replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        if ends_at: flight.ends_at=datetime.fromisoformat(ends_at).replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    except ValueError: raise HTTPException(422,"Invalid flight schedule date or time")
    db.add(AuditLog(staff_user_id=actor.id,target_user_id=None,action=f"FLIGHT_{new_status.value}",old_value=old,new_value={"status":new_status.value,"message":flight.status_message},reason=message.strip() or f"Flight marked {new_status.value}",security_metadata={"ip":request.client.host if request.client else None,"flight_id":flight.id}))
    db.commit()
    try: await discord_announce_update(settings,title=f"Flight {new_status.value.title()}",description=f"{actor.discord_display_name} updated {flight.flight_number}.",fields=[{"name":"Message","value":flight.status_message or "No additional message"}])
    except Exception: pass
    if new_status in {FlightStatus.CANCELLED,FlightStatus.DELAYED,FlightStatus.COMPLETED}:
        rows=db.execute(select(Booking,User).join(User,Booking.user_id==User.id).where(Booking.flight_id==flight.id,Booking.status=="CONFIRMED")).all(); emojis=await emoji_map()
        for booking,member in rows:
            if new_status==FlightStatus.CANCELLED:
                refund=booking.miles_used; member.miles_balance+=refund; booking.miles_refunded+=refund; booking.status="CANCELLED"; booking.cancelled_at=datetime.now(timezone.utc)
                content=f"{em(emojis,'Warning','⚠️')} Delta Air Lines | Flight Cancelled\n\nYour upcoming Delta flight has been cancelled.\n\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'Schedule','📅')} Original Departure: {flight.starts_at.strftime('%b %d, %Y at %H:%M UTC')}\n{em(emojis,'Ticket','🎟️')} Confirmation Number: {booking.confirmation_number}\n\nReason:\n{flight.status_message or 'Operational update'}\n\n{em(emojis,'CreditCard','💳')} SkyMiles Refunded: {refund:,}\n\nWe apologize for the inconvenience.\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
            elif new_status==FlightStatus.DELAYED:
                content=f"{em(emojis,'Timer','⏱️')} Delta Air Lines | Flight Delayed\n\nThere has been an update to your upcoming flight.\n\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'Schedule','📅')} Departure: {flight.starts_at.strftime('%b %d, %Y at %H:%M UTC')}\n{em(emojis,'Parking','🅿️')} Gate: {assigned(flight.gate)}\n\nReason:\n{flight.status_message or 'Operational update'}\n\nPlease check My Trips for the latest information.\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
            else:
                content=f"{em(emojis,'CheckMark','✅')} Delta Air Lines | Flight Completed\n\nThank you for flying with Delta Air Lines.\n\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'Schedule','📅')} Date: {flight.starts_at.strftime('%b %d, %Y')}\n{em(emojis,'CreditCard','💳')} SkyMiles Earned: To Be Reviewed\n{em(emojis,'CreditCard','💳')} Updated Balance: {member.miles_balance:,}\n\nYour completed flight appears in My Trips.\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
                booking.status="COMPLETED"
            db.commit(); await notify_member(db,member,flight,booking,f"FLIGHT_{new_status.value}",content,f"flight:{flight.id}:{new_status.value}:{event_token}:booking:{booking.id}")
            if new_status==FlightStatus.CANCELLED and refund:
                refund_content=f"{em(emojis,'CreditCard','💳')} Delta Air Lines | Refund Confirmed\n\nYour SkyMiles refund has been processed.\n\n{em(emojis,'Ticket','🎟️')} Confirmation Number: {booking.confirmation_number}\n{em(emojis,'Plane','✈️')} Flight: Delta {flight.flight_number}\n{em(emojis,'Maps','🗺️')} Route: {flight.departure_airport} → {flight.destination_airport}\n{em(emojis,'CreditCard','💳')} SkyMiles Refunded: {refund:,}\n{em(emojis,'CreditCard','💳')} Updated Balance: {member.miles_balance:,}\n\n{em(emojis,'WingPinLogo','🔺')} Keep Climbing, Delta Air Lines."
                await notify_member(db,member,flight,booking,"REFUND_CONFIRMED",refund_content,f"flight:{flight.id}:refund:{event_token}:booking:{booking.id}")
    changes=[]
    if old["gate"]!=flight.gate: changes.append(("GATE_CHANGE",f"{em(await emoji_map(),'Parking','🅿️')} Delta Air Lines | Gate Change\n\nYour departure gate has changed.\n\n✈️ Flight: Delta {flight.flight_number}\n🗺️ Route: {flight.departure_airport} → {flight.destination_airport}\n🅿️ Previous Gate: {assigned(old['gate'])}\n🅿️ New Gate: {assigned(flight.gate)}\n📅 Departure: {flight.starts_at.strftime('%b %d, %Y at %H:%M UTC')}"))
    if old["aircraft"]!=flight.aircraft: changes.append(("AIRCRAFT_CHANGE",f"✈️ Delta Air Lines | Aircraft Change\n\nThe aircraft assigned to your flight has changed.\n\n✈️ Flight: Delta {flight.flight_number}\n🗺️ Route: {flight.departure_airport} → {flight.destination_airport}\n✈️ Previous Aircraft: {assigned(old['aircraft'])}\n✈️ New Aircraft: {assigned(flight.aircraft)}\n📅 Departure: {flight.starts_at.strftime('%b %d, %Y at %H:%M UTC')}"))
    if old["starts_at"]!=flight.starts_at or old["ends_at"]!=flight.ends_at: changes.append(("SCHEDULE_CHANGE",f"📅 Delta Air Lines | Schedule Change\n\nYour flight schedule has been updated.\n\n✈️ Flight: Delta {flight.flight_number}\n🗺️ Route: {flight.departure_airport} → {flight.destination_airport}\n📅 Original Departure: {old['starts_at'].strftime('%b %d, %Y at %H:%M UTC')}\n📅 Updated Departure: {flight.starts_at.strftime('%b %d, %Y at %H:%M UTC')}\n📅 Original Arrival: {old['ends_at'].strftime('%b %d, %Y at %H:%M UTC') if old['ends_at'] else 'To Be Assigned'}\n📅 Updated Arrival: {flight.ends_at.strftime('%b %d, %Y at %H:%M UTC') if flight.ends_at else 'To Be Assigned'}"))
    if changes:
        rows=db.execute(select(Booking,User).join(User,Booking.user_id==User.id).where(Booking.flight_id==flight.id,Booking.status=="CONFIRMED")).all()
        for kind,text in changes:
            for booking,member in rows: await notify_member(db,member,flight,booking,kind,text+"\n\n🔺 Keep Climbing, Delta Air Lines.",f"flight:{flight.id}:{kind}:{event_token}:booking:{booking.id}")
    return RedirectResponse(f"{panel_path(permission(actor,settings))}?flight_updated=1",303)


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
