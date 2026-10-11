"""Authenticated API and durable event queue for the separate Delta Crew bot."""
from datetime import datetime, timezone
from pathlib import Path
import secrets
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .database import get_db
from .models import CrewDeliveryEvent, CommunityForm, Flight, FlightStatus

router=APIRouter()
settings=get_settings()


def authenticate(request: Request):
    expected=settings.delta_crew_api_secret
    supplied=request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if len(expected)<32 or not secrets.compare_digest(expected,supplied):
        raise HTTPException(401,"Crew bot authorization required")


def queue_event(db: Session, key: str, kind: str, payload: dict) -> CrewDeliveryEvent:
    """One notification per durable business event. Called before the parent commit."""
    event=db.scalar(select(CrewDeliveryEvent).where(CrewDeliveryEvent.event_key==key))
    if event:
        return event
    event=CrewDeliveryEvent(event_key=key,kind=kind,payload=payload,status="PENDING")
    db.add(event)
    return event


@router.get("/internal/crew/forms")
def list_published_forms(request:Request,db:Session=Depends(get_db)):
    authenticate(request)
    base=settings.app_url.rstrip("/")
    rows=db.scalars(select(CommunityForm).where(CommunityForm.status=="PUBLISHED")
                    .order_by(CommunityForm.updated_at.desc()).limit(100)).all()
    # Metadata is intentionally minimal. Discord-only role restrictions still apply
    # when an individual member opens the URL in a browser.
    return {"forms":[{"title":x.title,"url":base+"/forms/"+quote(x.slug,safe="")} for x in rows]}


@router.get("/internal/crew/flights")
def list_upcoming_flights(request:Request,db:Session=Depends(get_db)):
    authenticate(request)
    form=db.scalar(select(CommunityForm).where(CommunityForm.is_flight_form.is_(True)))
    base=settings.app_url.rstrip("/")
    flights=db.scalars(select(Flight).where(Flight.status.in_([FlightStatus.SCHEDULED,FlightStatus.DELAYED]))
                       .order_by(Flight.starts_at).limit(30)).all()
    return {"flights":[{"id":x.id,"number":x.flight_number,"departure":x.departure_airport,
                        "destination":x.destination_airport,"starts_at":x.starts_at.isoformat(),
                        "form_url":base+"/forms/"+form.slug+"?flight="+str(x.id) if form else base+"/forms"}
                       for x in flights]}


@router.get("/internal/crew/events")
def pending_events(request:Request,db:Session=Depends(get_db)):
    authenticate(request)
    rows=db.scalars(select(CrewDeliveryEvent).where(CrewDeliveryEvent.status=="PENDING")
                    .order_by(CrewDeliveryEvent.id).limit(50)).all()
    return {"events":[{"id":r.id,"kind":r.kind,"payload":r.payload} for r in rows]}


@router.post("/internal/crew/events/{event_id}/ack")
def acknowledge_event(request:Request,event_id:int,db:Session=Depends(get_db)):
    authenticate(request)
    row=db.get(CrewDeliveryEvent,event_id)
    if row is None:raise HTTPException(404,"Event not found")
    if row.status!="SENT":
        row.status="SENT"
        row.sent_at=datetime.now(timezone.utc)
        row.attempts+=1
        db.commit()
    return {"ok":True,"id":row.id,"status":row.status}
