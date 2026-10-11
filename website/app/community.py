"""Public-facing community forms, Discord-only accounts and bot-hosted flights.

Authorization for every read/write comes from Discord's current guild member roles.
No SkyMiles account is required for a form submission.
"""
import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import CommunityForm, CommunityFormResponse, Flight, FlightStatus, User
from .security import check_csrf, csrf_token, current_user
from .sheet_sync import enqueue_event, add_transaction
from .crew_bridge import queue_event

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
settings = get_settings()

FLIGHT_QUESTIONS = [
    {"id": "position", "label": "Requested flight position", "type": "select", "required": True,
     "options": ["Captain", "First Officer", "Cabin Crew", "Air Traffic Control", "Ground Crew", "Passenger"]},
    {"id": "roblox_name", "label": "Roblox username", "type": "text", "required": True, "options": []},
    {"id": "experience", "label": "Experience / qualifications", "type": "textarea", "required": False, "options": []},
    {"id": "notes", "label": "Additional notes", "type": "textarea", "required": False, "options": []},
]
QUESTION_TYPES = {"text", "textarea", "select", "radio", "checkbox", "number", "date"}
GUILDS = ("airlines", "crew")


async def memberships(discord_id: str) -> dict:
    """Fail closed when role verification is impossible; never trust saved role IDs."""
    if not settings.discord_bot_token:
        raise HTTPException(503, "Main Discord role verification is not configured")
    ids = {"airlines": settings.discord_guild_id, "crew": settings.discord_crew_guild_id}
    result = {}
    async with httpx.AsyncClient(timeout=10) as client:
        for name, guild_id in ids.items():
            if not guild_id:
                continue
            bot_token = settings.discord_bot_token if name == "airlines" else settings.discord_crew_bot_token
            # A missing Crew integration must not break Main Discord joining.
            # Crew-restricted forms stay unavailable until Crew credentials exist.
            if not bot_token:
                continue
            response = await client.get(
                "https://discord.com/api/v10/guilds/" + guild_id + "/members/" + discord_id,
                headers={"Authorization": "Bot " + bot_token},
            )
            if response.status_code == 404:
                continue
            if response.status_code != 200:
                raise HTTPException(503, "Discord role verification is temporarily unavailable")
            result[name] = [str(role) for role in response.json().get("roles", [])]
    return result


def identity(request: Request, db: Session) -> dict | None:
    if request.session.get("user_id"):
        user = current_user(request, db)
        return {"id": user.discord_user_id, "name": user.discord_display_name, "skymiles": True}
    guest = request.session.get("forms_identity")
    if isinstance(guest, dict) and str(guest.get("id", "")).isdigit():
        return {"id": str(guest["id"]), "name": str(guest.get("name", "Member"))[:100], "skymiles": False}
    return None


def authorize_login(request: Request) -> RedirectResponse:
    destination = request.url.path
    if request.url.query:
        destination += "?" + request.url.query
    return RedirectResponse("/auth/discord/forms?next=" + quote(destination, safe=""), 303)


async def verified_viewer(request: Request, db: Session) -> tuple[dict, dict] | RedirectResponse:
    viewer = identity(request, db)
    if not viewer:
        return authorize_login(request)
    roles = await memberships(viewer["id"])
    if not roles:
        raise HTTPException(403, "Please join the Delta Air Lines or Delta Crew Discord server to access this section")
    return viewer, roles


def access_level(roles: dict) -> str:
    checks = [
        ("OWNER", settings.owner_discord_role_ids, settings.crew_owner_role_ids),
        ("ADMIN", settings.admin_discord_role_ids, settings.crew_admin_role_ids),
        ("STAFF", settings.forms_staff_discord_role_ids, settings.crew_staff_role_ids),
    ]
    for level, airline_ids, crew_ids in checks:
        if set(roles.get("airlines", [])) & settings.ids(airline_ids):
            return level
        if set(roles.get("crew", [])) & settings.ids(crew_ids):
            return level
    return "MEMBER"


def can_see(form: CommunityForm, roles: dict) -> bool:
    if form.status != "PUBLISHED":
        return False
    restricted = form.allowed_roles or {}
    if not any(restricted.get(guild) for guild in GUILDS):
        return True
    return any(set(map(str, restricted.get(guild, []))) & set(roles.get(guild, [])) for guild in GUILDS)


async def role_catalog() -> dict:
    if not settings.discord_bot_token:
        raise HTTPException(503, "Discord role catalog is not configured")
    guilds = {"airlines": settings.discord_guild_id, "crew": settings.discord_crew_guild_id}
    result = {}
    async with httpx.AsyncClient(timeout=10) as client:
        for guild, guild_id in guilds.items():
            if not guild_id:
                continue
            bot_token = settings.discord_bot_token if guild == "airlines" else settings.discord_crew_bot_token
            if not bot_token:
                continue
            response = await client.get("https://discord.com/api/v10/guilds/" + guild_id + "/roles",
                                        headers={"Authorization": "Bot " + bot_token})
            if response.status_code != 200:
                raise HTTPException(503, "Unable to load Discord roles")
            result[guild] = [{"id": str(r["id"]), "name": r["name"]} for r in response.json()
                             if r["name"] != "@everyone"]
    return result


def page_context(request: Request, viewer: dict, roles: dict, **kwargs):
    return {"request": request, "viewer": viewer, "access": access_level(roles),
            "csrf": csrf_token(request), "settings": settings, **kwargs}


def ensure_flight_form(db: Session, creator: str = "system") -> CommunityForm:
    existing = db.scalar(select(CommunityForm).where(CommunityForm.is_flight_form.is_(True)).order_by(CommunityForm.id).limit(1))
    if existing:
        return existing
    form = CommunityForm(slug="flight-crew-fillout", title="Flight Crew Fillout",
                         description="Complete this form for a hosted Delta Air Lines flight.",
                         questions=FLIGHT_QUESTIONS, allowed_roles={}, status="PUBLISHED",
                         is_flight_form=True, created_by_discord_id=creator)
    db.add(form)
    db.flush()
    enqueue_form(db, form)
    return form


def enqueue_form(db: Session, form: CommunityForm):
    data = {"form_id": form.id, "slug": form.slug, "title": form.title, "status": form.status,
            "allowed_roles": form.allowed_roles, "questions": form.questions,
            "updated_at": datetime.now(timezone.utc).isoformat()}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:18]
    enqueue_event(db, "forms:" + str(form.id) + ":" + digest, "form_upsert", data)
    if form.status == "PUBLISHED":
        queue_event(db, "crew:form:" + str(form.id) + ":" + digest, "form_published", {"title":form.title, "url":settings.app_url.rstrip("/")+"/forms/"+form.slug, "restricted":any((form.allowed_roles or {}).get(g) for g in GUILDS)})


def enqueue_flight(db: Session, flight: Flight):
    data = {"flight_id": flight.id, "flight_number": flight.flight_number,
            "departure": flight.departure_airport, "destination": flight.destination_airport,
            "aircraft": flight.aircraft or "", "gate": flight.gate or "",
            "host_discord_id": flight.hosted_by_discord_id or "",
            "starts_at": flight.starts_at.isoformat(), "ends_at": flight.ends_at.isoformat() if flight.ends_at else "",
            "status": flight.status.value, "name": flight.name}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:18]
    enqueue_event(db, "flights:" + str(flight.id) + ":" + digest, "flight_upsert", data)
    queue_event(db, "crew:flight:" + str(flight.id) + ":" + digest, "flight", {**data, "form_url":settings.app_url.rstrip("/")+"/forms/flight-crew-fillout?flight="+str(flight.id)})


@router.get("/forms", response_class=HTMLResponse)
async def forms_index(request: Request, db: Session = Depends(get_db)):
    result = await verified_viewer(request, db)
    if isinstance(result, RedirectResponse):
        return result
    viewer, roles = result
    level = access_level(roles)
    all_forms = db.scalars(select(CommunityForm).order_by(CommunityForm.updated_at.desc())).all()
    visible = all_forms if level != "MEMBER" else [form for form in all_forms if can_see(form, roles)]
    return templates.TemplateResponse("forms/index.html",
                                      page_context(request, viewer, roles, forms=visible))


@router.get("/forms/new", response_class=HTMLResponse)
@router.get("/forms/{slug}/edit", response_class=HTMLResponse)
async def form_editor(request: Request, slug: str | None = None, db: Session = Depends(get_db)):
    result = await verified_viewer(request, db)
    if isinstance(result, RedirectResponse):
        return result
    viewer, roles = result
    if access_level(roles) == "MEMBER":
        raise HTTPException(403, "Staff permissions are required")
    form = db.scalar(select(CommunityForm).where(CommunityForm.slug == slug)) if slug else None
    if slug and not form:
        raise HTTPException(404, "Form not found")
    return templates.TemplateResponse("forms/editor.html",
        page_context(request, viewer, roles, form=form, catalog=await role_catalog(),
                     defaults=FLIGHT_QUESTIONS))


@router.post("/forms/manage")
async def save_form(request: Request, csrf: str = Form(...), payload: str = Form(...),
                    db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    result = await verified_viewer(request, db)
    if isinstance(result, RedirectResponse):
        raise HTTPException(401, "Sign in first")
    viewer, roles = result
    if access_level(roles) == "MEMBER":
        raise HTTPException(403, "Staff permissions are required")
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Invalid form")
        title = str(data["title"]).strip()[:180]
        description = str(data.get("description", "")).strip()[:3000]
        state = str(data.get("status", "DRAFT")).upper()
        question_data = data.get("questions", [])
        if not title or state not in {"DRAFT", "PUBLISHED", "CLOSED"}:
            raise ValueError("Title and valid status are required")
        if not isinstance(question_data, list) or not 1 <= len(question_data) <= 50:
            raise ValueError("Forms require between 1 and 50 questions")
        questions = []
        seen = set()
        for question in question_data:
            key = str(question.get("id", ""))[:40]
            label = str(question.get("label", "")).strip()[:200]
            kind = str(question.get("type", "text"))
            options = question.get("options", [])
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", key) or key in seen or not label or kind not in QUESTION_TYPES:
                raise ValueError("Invalid or duplicate question")
            if not isinstance(options, list) or len(options) > 30:
                raise ValueError("Too many choices")
            options = [str(choice).strip()[:150] for choice in options if str(choice).strip()]
            if kind in {"select", "radio"} and not options:
                raise ValueError("Multiple-choice questions need choices")
            questions.append({"id": key, "label": label, "type": kind,
                              "required": bool(question.get("required")), "options": options})
            seen.add(key)
        restrictions = data.get("allowed_roles", {})
        if not isinstance(restrictions, dict):
            raise ValueError("Invalid permissions")
        clean_roles = {}
        catalog = await role_catalog()
        for guild in GUILDS:
            selected = restrictions.get(guild, [])
            valid = {role["id"] for role in catalog.get(guild, [])}
            if not isinstance(selected, list) or len(selected) > 30 or any(str(item) not in valid for item in selected):
                raise ValueError("Choose valid Discord roles")
            clean_roles[guild] = [str(role_id) for role_id in selected]
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(422, str(error))
    existing_id = data.get("id")
    form = db.get(CommunityForm, existing_id) if isinstance(existing_id, int) else None
    if existing_id and not form:
        raise HTTPException(404, "Original form not found")
    if not form:
        form = CommunityForm(slug="form-" + uuid4().hex[:14],
                             created_by_discord_id=viewer["id"], questions=[], allowed_roles={})
        db.add(form)
    form.title, form.description, form.questions = title, description, questions
    form.status, form.allowed_roles = state, clean_roles
    db.flush()
    enqueue_form(db, form)
    db.commit()
    return RedirectResponse("/forms/" + form.slug + "/edit?saved=1", 303)


@router.get("/forms/{slug}", response_class=HTMLResponse)
async def open_form(request: Request, slug: str, flight: int | None = None,
                    db: Session = Depends(get_db)):
    result = await verified_viewer(request, db)
    if isinstance(result, RedirectResponse):
        return result
    viewer, roles = result
    form = db.scalar(select(CommunityForm).where(CommunityForm.slug == slug))
    if not form:
        raise HTTPException(404, "Form not found")
    if not can_see(form, roles) and access_level(roles) == "MEMBER":
        raise HTTPException(403, "This form is closed or restricted to selected Discord roles")
    related = db.get(Flight, flight) if flight and form.is_flight_form else None
    if flight and not related:
        raise HTTPException(404, "Flight not found")
    open_flights = db.scalars(select(Flight).where(Flight.status.in_([FlightStatus.SCHEDULED, FlightStatus.DELAYED])).order_by(Flight.starts_at)).all() if form.is_flight_form and related is None else []
    return templates.TemplateResponse("forms/answer.html",
        page_context(request, viewer, roles, form=form, flight=related,
                     open_flights=open_flights, submission_key=uuid4().hex))


@router.post("/forms/{slug}/submit")
async def submit_form(request: Request, slug: str, csrf: str = Form(...),
                      submission_key: str = Form(...), flight_id: str = Form(""),
                      db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    result = await verified_viewer(request, db)
    if isinstance(result, RedirectResponse):
        raise HTTPException(401, "Sign in first")
    viewer, roles = result
    form = db.scalar(select(CommunityForm).where(CommunityForm.slug == slug))
    if not form or not can_see(form, roles):
        raise HTTPException(403, "This form is not available for your Discord roles")
    if not re.fullmatch(r"[0-9a-f]{32}", submission_key):
        raise HTTPException(422, "Invalid submission identifier")
    if db.scalar(select(CommunityFormResponse.id).where(CommunityFormResponse.submission_key == submission_key)):
        return RedirectResponse("/forms?submitted=1", 303)
    related = db.get(Flight, int(flight_id)) if flight_id.isdigit() and form.is_flight_form else None
    if flight_id and not related:
        raise HTTPException(422, "Invalid flight")
    incoming = await request.form()
    answers = {}
    for question in form.questions:
        key = "answer_" + question["id"]
        values = incoming.getlist(key)
        kind = question["type"]
        if kind == "checkbox":
            chosen = [str(value)[:150] for value in values]
            answer = chosen
        else:
            answer = str(values[0]).strip()[:2000] if values else ""
        if question["required"] and not answer:
            raise HTTPException(422, "Required: " + question["label"])
        if kind in {"select", "radio"} and answer and answer not in question["options"]:
            raise HTTPException(422, "Invalid selection for " + question["label"])
        if kind == "number" and answer:
            try:
                float(answer)
            except ValueError:
                raise HTTPException(422, "Invalid number for " + question["label"])
        answers[question["id"]] = answer
    response = CommunityFormResponse(submission_key=submission_key, form_id=form.id,
        flight_id=related.id if related else None, discord_user_id=viewer["id"],
        discord_display_name=viewer["name"], answers=answers)
    db.add(response)
    db.flush()
    enqueue_event(db, "forms:response:" + submission_key, "form_response",
                  {"response_id": response.id, "form_id": form.id, "form_title": form.title,
                   "discord_user_id": viewer["id"], "discord_display_name": viewer["name"],
                   "flight_id": response.flight_id, "is_flight_form": form.is_flight_form, "roles": roles, "answers": answers,
                   "submitted_at": datetime.now(timezone.utc).isoformat()})
    queue_event(db, "crew:response:" + submission_key, "form_response", {
        "response_id": response.id, "display_name": viewer["name"], "form_title": form.title,
        "responses_url": settings.app_url.rstrip("/")+"/forms/"+form.slug+"/responses"
    })
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return RedirectResponse("/forms?submitted=1", 303)


@router.get("/forms/{slug}/responses", response_class=HTMLResponse)
async def view_responses(request: Request, slug: str, db: Session = Depends(get_db)):
    result = await verified_viewer(request, db)
    if isinstance(result, RedirectResponse):
        return result
    viewer, roles = result
    if access_level(roles) == "MEMBER":
        raise HTTPException(403, "Staff only")
    form = db.scalar(select(CommunityForm).where(CommunityForm.slug == slug))
    if not form:
        raise HTTPException(404, "Form not found")
    records = db.scalars(select(CommunityFormResponse).where(CommunityFormResponse.form_id == form.id)
                         .order_by(CommunityFormResponse.submitted_at.desc()).limit(500)).all()
    return templates.TemplateResponse("forms/responses.html",
        page_context(request, viewer, roles, form=form, records=records))


@router.post("/internal/flights/host")
async def hosted_flight(request: Request, db: Session = Depends(get_db)):
    """Called only by deltaptfs-bot. Never by browsers using a Discord user ID."""
    secret = settings.delta_flight_api_secret
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if len(secret) < 32 or not secrets.compare_digest(secret, supplied):
        raise HTTPException(401, "Unauthorized")
    data = await request.json()
    event_id = str(data.get("event_id", ""))
    number = str(data.get("flight_number", "")).upper().strip()
    departure = str(data.get("departure", "")).upper().strip()
    destination = str(data.get("destination", "")).upper().strip()
    if not re.fullmatch(r"[0-9]{15,22}", event_id) or not re.fullmatch(r"[A-Z]{2,4}\s?\d{1,4}", number):
        raise HTTPException(422, "Invalid flight identifier")
    if not re.fullmatch(r"[A-Z0-9]{3,4}", departure) or not re.fullmatch(r"[A-Z0-9]{3,4}", destination) or departure == destination:
        raise HTTPException(422, "Invalid route")
    try:
        starts = datetime.fromisoformat(str(data["starts_at"]).replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "An ISO date with UTC offset is required")
    if starts.tzinfo is None:
        raise HTTPException(422, "Departure must include timezone")
    source_id = "bot-" + event_id
    flight = db.scalar(select(Flight).where(Flight.discord_event_id == source_id))
    if not flight:
        flight = Flight(discord_event_id=source_id, flight_number=number, name=number,
                        starts_at=starts, location=departure + " → " + destination)
        db.add(flight)
    flight.flight_number = number
    flight.hosted_by_discord_id = str(data.get("host_discord_id") or "")[:32] or None
    flight.name = str(data.get("name") or number)[:120]
    flight.departure_airport, flight.destination_airport = departure, destination
    flight.aircraft = str(data.get("aircraft") or "")[:100] or None
    flight.gate = str(data.get("gate") or "")[:30] or None
    flight.starts_at = starts
    flight.location = departure + " → " + destination
    flight.description = str(data.get("description") or "Delta Air Lines hosted flight")[:1000]
    flight.status = FlightStatus.SCHEDULED
    db.flush()
    form = ensure_flight_form(db, str(data.get("host_discord_id", "system"))[:32])
    enqueue_flight(db, flight)
    db.commit()
    base_url = str(settings.app_url).rstrip("/")
    return JSONResponse({"ok": True, "flight_id": flight.id,
                         "form_url": base_url + "/forms/" + form.slug + "?flight=" + str(flight.id),
                         "booking_url": base_url + "/flights", "flight_number": number})


def internal_secret(request: Request):
    secret = settings.delta_flight_api_secret
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if len(secret) < 32 or not secrets.compare_digest(secret, supplied):
        raise HTTPException(401, "Unauthorized")


@router.post("/internal/skymiles/{action}")
async def internal_skymiles(request: Request, action: str, db: Session = Depends(get_db)):
    """One authoritative balance for bot and website; Sheets is a mirror."""
    internal_secret(request)
    if action not in {"balance", "leaderboard", "award"}:
        raise HTTPException(404, "Unknown SkyMiles action")
    data = await request.json()
    if action == "leaderboard":
        users = db.scalars(select(User).order_by(User.miles_balance.desc()).limit(10)).all()
        return {"leaders": [{"userId": user.discord_user_id, "displayName": user.discord_display_name,
                             "balance": user.miles_balance} for user in users]}
    discord_id = str(data.get("user_id") or "")
    if not re.fullmatch(r"\d{15,22}", discord_id):
        raise HTTPException(422, "Invalid Discord ID")
    user = db.scalar(select(User).where(User.discord_user_id == discord_id).with_for_update())
    if not user:
        raise HTTPException(404, "This member must enroll in SkyMiles before their balance can be changed")
    if action == "balance":
        return {"userId": discord_id, "balance": user.miles_balance}
    amount = data.get("miles")
    reason = str(data.get("reason") or "").strip()[:255]
    actor_id = str(data.get("awarded_by_id") or "")
    if isinstance(amount, bool) or not isinstance(amount, int) or not -1000000 <= amount <= 1000000 or amount == 0 or not reason:
        raise HTTPException(422, "Provide a nonzero amount and reason")
    if not re.fullmatch(r"\d{15,22}", actor_id):
        raise HTTPException(422, "Invalid award author")
    actor = db.scalar(select(User).where(User.discord_user_id == actor_id))
    before = user.miles_balance
    after = max(0, before + amount)
    changed = after - before
    user.miles_balance = after
    if changed > 0:
        user.lifetime_miles += changed
    add_transaction(db, user, type="BOT_AWARD" if changed > 0 else "BOT_CORRECTION",
                    description=reason, reference=str(data.get("flight_id") or "")[:100],
                    miles_change=changed, balance_before=before, balance_after=after, actor=actor)
    db.commit()
    return {"userId": discord_id, "balance": after, "actual_change": changed}


@router.get("/internal/flights/{flight_id}")
async def internal_flight_details(request:Request,flight_id:int,db:Session=Depends(get_db)):
    """Main bot retrieves canonical flight data instead of typing it repeatedly."""
    internal_secret(request)
    flight=db.get(Flight,flight_id)
    if not flight:raise HTTPException(404,"Flight not found")
    form=ensure_flight_form(db)
    db.commit()
    return {"id":flight.id,"flight_number":flight.flight_number,"departure":flight.departure_airport,
            "destination":flight.destination_airport,"aircraft":flight.aircraft,"gate":flight.gate,
            "starts_at":flight.starts_at.isoformat(),"ends_at":flight.ends_at.isoformat() if flight.ends_at else None,
            "status":flight.status.value,"status_message":flight.status_message,
            "name":flight.name,"miles_reward":flight.miles_reward,"image_url":flight.image_url,
            "operator":"Delta Air Lines","event_id":flight.discord_event_id,
            "form_url":settings.app_url.rstrip("/")+"/forms/"+form.slug+"?flight="+str(flight.id)}


@router.post("/internal/flights/{flight_id}/status")
async def internal_flight_update(request:Request,flight_id:int,db:Session=Depends(get_db)):
    """Apply a format update after staff confirms publication in Discord."""
    internal_secret(request)
    flight=db.scalar(select(Flight).where(Flight.id==flight_id).with_for_update())
    if not flight:raise HTTPException(404,"Flight not found")
    data=await request.json()
    state=str(data.get("status") or "").upper()
    valid={"SCHEDULED","DELAYED","CANCELLED","COMPLETED","CHECKIN_OPEN","CHECKIN_CLOSED"}
    if state not in valid:raise HTTPException(422,"Unknown flight state")
    mapping={"DELAYED":FlightStatus.DELAYED,"CANCELLED":FlightStatus.CANCELLED,
             "COMPLETED":FlightStatus.COMPLETED,"SCHEDULED":FlightStatus.SCHEDULED}
    if state in mapping:flight.status=mapping[state]
    if state.startswith("CHECKIN"):flight.status_message=state
    elif str(data.get("reason") or "").strip():flight.status_message=str(data["reason"])[:400]
    when=data.get("starts_at")
    if when:
        try:value=datetime.fromisoformat(str(when).replace("Z","+00:00"))
        except ValueError:raise HTTPException(422,"Departure time is invalid")
        if value.tzinfo is None:raise HTTPException(422,"Departure must have timezone")
        flight.starts_at=value.astimezone(timezone.utc)
    enqueue_flight(db,flight)
    db.commit()
    return {"ok":True,"flight_id":flight.id,"status":flight.status.value}
