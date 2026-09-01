import asyncio
import re
from uuid import uuid4
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
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
from .database import Base, SessionLocal, engine, get_db
from .models import AuditLog, Booking, Flight, FlightStatus, Redemption, Reward, Status, Tier, TierConfig, Transaction, User
from .oauth import discord_authorize, discord_identity, discord_remove_skymiles_roles, discord_scheduled_events, discord_set_medallion_roles, roblox_authorize, roblox_identity
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
                db.add(TierConfig(tier=tier, miles_threshold=miles, mqp_threshold=mqp, segments_threshold=segments, description=description, benefits=benefits, enrollment_cost=miles))
            for name, desc, cost in [("Priority Boarding","Board first at a community flight.",2500),("Flight Upgrade","Upgrade an eligible roleplay itinerary.",5000),("Exclusive Discord Role","Unlock a distinguished community role.",10000),("Special Aircraft Access","Access a featured community aircraft.",15000)]: db.add(Reward(name=name, description=desc, miles_cost=cost, active=True))
            db.commit()
    await expire_medallions_once()
    expiration_task = asyncio.create_task(medallion_expiration_worker())
    try:
        yield
    finally:
        expiration_task.cancel()


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
    db.refresh(user)
    try: await discord_set_medallion_roles(settings, user.discord_user_id, user.tier.name if user.tier != Tier.MEMBER else None)
    except Exception: pass  # Account creation must survive a temporary Discord role outage.
    request.session.clear(); request.session["user_id"]=user.id; request.session["authorization"]=permission(user,settings)
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


@app.get("/settings", response_class=HTMLResponse)
def account_settings(request:Request,db:Session=Depends(get_db)):
    user=current_user(request,db)
    return templates.TemplateResponse("settings.html",context(request,user=user,theme=request.session.get("theme","light"),auth=permission(user,settings)))


@app.post("/settings/theme")
def update_theme(request:Request,theme:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); current_user(request,db)
    if theme not in {"light","dark","system"}: raise HTTPException(422,"Invalid theme")
    request.session["theme"]=theme
    return RedirectResponse("/settings?theme_saved=1",303)


@app.post("/settings/quit")
@limiter.limit("2/hour")
async def quit_skymiles(request:Request,confirmation:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    if confirmation.strip().upper() != "QUIT": raise HTTPException(422,"Type QUIT to confirm")
    user.account_status=Status.DISABLED
    db.add(AuditLog(staff_user_id=user.id,target_user_id=user.id,action="MEMBERSHIP_ENDED",old_value={"status":"ACTIVE","tier":user.tier.value},new_value={"status":"DISABLED"},reason="Member voluntarily left the SkyMiles program",security_metadata={"ip":request.client.host if request.client else None,"self_service":True}))
    db.commit()
    try: await discord_remove_skymiles_roles(settings,user.discord_user_id)
    except Exception: pass
    request.session.clear()
    response=RedirectResponse("/?membership_ended=1",303); response.delete_cookie("skymiles_session"); return response


@app.get("/medallions/{tier_name}", response_class=HTMLResponse)
def medallion_detail(request:Request,tier_name:str,db:Session=Depends(get_db)):
    user=current_user(request,db)
    try: desired=Tier[tier_name.upper()]
    except KeyError: raise HTTPException(404,"Medallion tier not found")
    if desired == Tier.MEMBER: raise HTTPException(404,"Medallion tier not found")
    tier=db.scalar(select(TierConfig).where(TierConfig.tier==desired))
    if not tier: raise HTTPException(404,"Medallion tier not found")
    qualifies=user.lifetime_miles>=tier.miles_threshold and user.medallion_qualifying_points>=tier.mqp_threshold and user.segments_flown>=tier.segments_threshold
    return templates.TemplateResponse("medallion_detail.html",context(request,user=user,tier=tier,qualifies=qualifies,auth=permission(user,settings)))


def eligible_amenities(user: User) -> list[dict]:
    amenities = [{"id":"fast_booking","name":"Fast Booking","description":"Priority handling for this flight booking."}]
    if user.tier in {Tier.GOLD, Tier.PLATINUM, Tier.DIAMOND}: amenities.append({"id":"priority_boarding","name":"Priority Boarding","description":"Board in the Medallion priority group."})
    if user.tier in {Tier.PLATINUM, Tier.DIAMOND}: amenities.append({"id":"upgrade_priority","name":"Upgrade Priority","description":"Apply upgrade priority to this flight only."})
    if user.tier == Tier.DIAMOND: amenities.append({"id":"diamond_service","name":"Diamond Service","description":"Highest community service priority."})
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
    try: await sync_flights(db)
    except Exception: pass
    available=db.scalars(select(Flight).where(Flight.status.in_([FlightStatus.SCHEDULED,FlightStatus.DELAYED])).order_by(Flight.starts_at)).all()
    booked=set(db.scalars(select(Booking.flight_id).where(Booking.user_id==user.id)).all())
    return templates.TemplateResponse("flights.html",context(request,user=user,flights=available,booked=booked,amenities=eligible_amenities(user),auth=permission(user,settings)))


@app.post("/flights/{flight_id}/book")
@limiter.limit("10/minute")
def book_flight(request:Request,flight_id:int,csrf:str=Form(...),amenities:list[str]=Form(default=[]),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    flight=db.get(Flight,flight_id)
    if not flight or flight.status in {FlightStatus.CANCELLED,FlightStatus.COMPLETED}: raise HTTPException(400,"This flight is not available for booking")
    allowed={item["id"] for item in eligible_amenities(user)}
    selected=[item for item in amenities if item in allowed]
    existing=db.scalar(select(Booking).where(Booking.flight_id==flight.id,Booking.user_id==user.id))
    if existing: existing.amenities=selected; existing.status="CONFIRMED"
    else: db.add(Booking(flight_id=flight.id,user_id=user.id,amenities=selected))
    db.commit(); return RedirectResponse("/flights?booked=1",303)


@app.post("/tiers/{tier_name}/join")
@limiter.limit("5/minute")
async def join_tier(request:Request,tier_name:str,csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); user=current_user(request,db)
    try: desired=Tier[tier_name.upper()]
    except KeyError: raise HTTPException(404,"Medallion tier not found")
    with db.begin_nested():
        user=db.scalar(select(User).where(User.id==user.id).with_for_update())
        config=db.scalar(select(TierConfig).where(TierConfig.tier==desired))
        if not config or user.lifetime_miles < config.miles_threshold or user.medallion_qualifying_points < config.mqp_threshold or user.segments_flown < config.segments_threshold:
            raise HTTPException(403,"You have not met all requirements for this Medallion level")
        if user.miles_balance < config.enrollment_cost: raise HTTPException(400,"Not Enough Miles")
        before=user.miles_balance; user.miles_balance-=config.enrollment_cost
        user.tier=desired; user.medallion_expires_at=next_medallion_expiration()
        db.add(Transaction(user_id=user.id,type="MEDALLION_ENROLLMENT",description=f"Joined {desired.value}",reference=desired.name,miles_change=-config.enrollment_cost,balance_before=before,balance_after=user.miles_balance,created_by=user.id))
    db.commit()
    try: await discord_set_medallion_roles(settings,user.discord_user_id,desired.name)
    except Exception: raise HTTPException(502,"Status updated, but Discord role synchronization needs staff attention")
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


def require_staff(request,db):
    user=current_user(request,db)
    if permission(user,settings) not in {"STAFF","ADMIN","OWNER"}: raise HTTPException(403,"Access denied")
    return user


@app.get("/admin",response_class=HTMLResponse)
def admin(request:Request,q:str="",db:Session=Depends(get_db)):
    actor=require_staff(request,db); users=[]
    if q: users=db.scalars(select(User).where(or_(User.discord_display_name.ilike(f"%{q}%"),User.discord_username.ilike(f"%{q}%"),User.discord_user_id==q,User.roblox_username.ilike(f"%{q}%"),User.roblox_user_id==q,User.skymiles_number.ilike(f"%{q}%"))).limit(25)).all()
    flights=db.scalars(select(Flight).order_by(Flight.starts_at.desc()).limit(20)).all()
    return templates.TemplateResponse("admin.html",context(request,user=actor,users=users,flights=flights,auth=permission(actor,settings)))


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


@app.post("/admin/flights/sync")
async def admin_sync_flights(request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); require_staff(request,db)
    await sync_flights(db)
    return RedirectResponse("/admin?flights_synced=1",303)


@app.post("/admin/flights/create")
def admin_create_flight(request:Request,flight_number:str=Form(...),departure_airport:str=Form(...),destination_airport:str=Form(...),name:str=Form(...),starts_at:str=Form(...),miles_reward:int=Form(...),description:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=require_staff(request,db)
    number=" ".join(flight_number.upper().split()); departure=departure_airport.upper().strip(); destination=destination_airport.upper().strip()
    if not re.fullmatch(r"[A-Z]{2,4} ?\d{1,4}",number): raise HTTPException(422,"Use a flight number such as DAL 1234")
    if not re.fullmatch(r"[A-Z0-9]{3,4}",departure) or not re.fullmatch(r"[A-Z0-9]{3,4}",destination): raise HTTPException(422,"Use valid 3–4 character airport codes")
    if departure==destination: raise HTTPException(422,"Departure and destination must be different")
    if miles_reward < 0 or miles_reward > 100_000: raise HTTPException(422,"Miles reward must be between 0 and 100,000")
    try: departure_time=datetime.fromisoformat(starts_at).replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    except ValueError: raise HTTPException(422,"Invalid departure date and time")
    flight=Flight(discord_event_id=f"manual-{uuid4().hex[:24]}",flight_number=number,departure_airport=departure,destination_airport=destination,name=name.strip()[:120],description=description.strip()[:1000],location=f"{departure} → {destination}",starts_at=departure_time,miles_reward=miles_reward,status=FlightStatus.SCHEDULED)
    db.add(flight); db.flush()
    db.add(AuditLog(staff_user_id=actor.id,target_user_id=None,action="FLIGHT_CREATED",old_value=None,new_value={"flight_id":flight.id,"number":number,"route":f"{departure}-{destination}","miles_reward":miles_reward},reason="Staff-created community flight",security_metadata={"ip":request.client.host if request.client else None}))
    db.commit(); return RedirectResponse("/admin?flight_created=1",303)


@app.post("/admin/flights/{flight_id}/status")
def admin_flight_status(request:Request,flight_id:int,status:str=Form(...),message:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    check_csrf(request,csrf); actor=require_staff(request,db)
    try: new_status=FlightStatus[status.upper()]
    except KeyError: raise HTTPException(422,"Invalid flight status")
    flight=db.get(Flight,flight_id)
    if not flight: raise HTTPException(404,"Flight not found")
    old={"status":flight.status.value,"message":flight.status_message}
    flight.status=new_status; flight.status_message=message.strip()[:500] or None
    if new_status == FlightStatus.COMPLETED:
        bookings=db.scalars(select(Booking).where(Booking.flight_id==flight.id,Booking.status=="CONFIRMED").with_for_update()).all()
        for booking in bookings:
            member=db.scalar(select(User).where(User.id==booking.user_id).with_for_update())
            before=member.miles_balance; member.miles_balance+=flight.miles_reward; member.lifetime_miles+=flight.miles_reward; member.segments_flown+=1; booking.status="REWARDED"
            db.add(Transaction(user_id=member.id,type="FLIGHT_COMPLETED",description=f"{flight.flight_number} · {flight.departure_airport} → {flight.destination_airport}",reference=flight.flight_number,miles_change=flight.miles_reward,balance_before=before,balance_after=member.miles_balance,created_by=actor.id))
    db.add(AuditLog(staff_user_id=actor.id,target_user_id=None,action=f"FLIGHT_{new_status.value}",old_value=old,new_value={"status":new_status.value,"message":flight.status_message},reason=message.strip() or f"Flight marked {new_status.value}",security_metadata={"ip":request.client.host if request.client else None,"flight_id":flight.id}))
    db.commit(); return RedirectResponse("/admin?flight_updated=1",303)


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
