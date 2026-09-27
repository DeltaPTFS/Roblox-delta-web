"""Reliable one-way mirroring from the website database to the Delta Main Bot.

PostgreSQL is the source of truth.  This module only writes immutable outbox
records in the same transaction as website changes, then delivers them after
commit.  Google Sheets is never queried while calculating a balance.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .database import SessionLocal
from .models import SheetSyncEvent, Transaction, User

logger = logging.getLogger("skymiles.sheet_sync")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def stable_event_id(event_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"delta-skymiles-website:{event_key}"))


def member_payload(user: User, *, registered_by: User | None = None, notes: str = "") -> dict:
    registrar = registered_by or user
    return {
        "timestamp": _iso(user.created_at),
        "skymiles_number": user.skymiles_number,
        "discord_user_id": user.discord_user_id,
        "discord_username": user.discord_username,
        "roblox_user_id": user.roblox_user_id,
        "roblox_username": user.roblox_username,
        "rp_name": user.roblox_display_name or user.discord_display_name,
        "membership_tier": _value(user.tier),
        "registration_status": _value(user.account_status),
        "registered_by_discord_id": registrar.discord_user_id,
        "registered_by_name": registrar.discord_display_name,
        "source": "Website",
        "notes": notes,
        "website_user_id": user.id,
        "miles_balance": user.miles_balance,
        "lifetime_miles": user.lifetime_miles,
        "mqp": user.medallion_qualifying_points,
        "segments": user.segments_flown,
    }


def transaction_payload(transaction: Transaction, user: User, actor: User | None = None, *, notes: str = "") -> dict:
    return {
        "timestamp": _iso(transaction.created_at),
        "transaction_id": transaction.id,
        "skymiles_number": user.skymiles_number,
        "discord_user_id": user.discord_user_id,
        "display_name": user.discord_display_name,
        "miles_change": transaction.miles_change,
        "balance_after": transaction.balance_after,
        "flight_or_event_id": transaction.reference or "",
        "reason": transaction.description,
        "awarded_by_discord_id": actor.discord_user_id if actor else "",
        "awarded_by_name": actor.discord_display_name if actor else "Website System",
        "entry_type": transaction.type,
        "notes": notes,
        "website_user_id": user.id,
    }


def enqueue_event(db: Session, event_key: str, event_type: str, payload: dict, *, replay: bool = False) -> tuple[SheetSyncEvent, bool]:
    """Create an event once; optionally make an existing event deliverable again."""
    existing = db.scalar(select(SheetSyncEvent).where(SheetSyncEvent.event_key == event_key))
    now = datetime.now(timezone.utc)
    if existing:
        if replay:
            existing.payload = payload
            existing.status = "PENDING"
            existing.next_attempt_at = now
            existing.locked_at = None
            existing.last_error = None
        logger.info("Sheet sync duplicate ignored event_key=%s replay=%s", event_key, replay)
        return existing, False
    event = SheetSyncEvent(
        id=stable_event_id(event_key), event_key=event_key, event_type=event_type,
        payload=payload, status="PENDING", next_attempt_at=now,
    )
    db.add(event)
    return event, True


def enqueue_registration(db: Session, user: User, registered_by: User | None = None, *, replay: bool = False) -> SheetSyncEvent:
    event, _ = enqueue_event(
        db, f"registration:{user.id}", "register_member",
        member_payload(user, registered_by=registered_by, notes="Website OAuth registration"), replay=replay,
    )
    return event


def enqueue_member_update(db: Session, user: User, reason: str, actor: User | None = None, *, replay: bool = False) -> SheetSyncEvent:
    state = {
        "tier": _value(user.tier), "status": _value(user.account_status),
        "balance": user.miles_balance, "mqp": user.medallion_qualifying_points,
        "segments": user.segments_flown, "reason": reason,
    }
    digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:20]
    payload = member_payload(user, registered_by=actor, notes=reason)
    payload["update_reason"] = reason
    event, _ = enqueue_event(db, f"member:{user.id}:state:{digest}", "update_member", payload, replay=replay)
    return event


def enqueue_transaction(db: Session, transaction: Transaction, user: User, actor: User | None = None, *, replay: bool = False) -> SheetSyncEvent:
    if transaction.id is None:
        db.flush()
    event, _ = enqueue_event(
        db, f"transaction:{transaction.id}", "record_transaction",
        transaction_payload(transaction, user, actor), replay=replay,
    )
    return event


def add_transaction(db: Session, user: User, *, type: str, description: str, reference: str | None,
                    miles_change: int, balance_before: int, balance_after: int,
                    actor: User | None = None, notes: str = "") -> Transaction:
    """Persist an authoritative ledger row and its mirror event together."""
    transaction = Transaction(
        user_id=user.id, type=type, description=description, reference=reference,
        miles_change=miles_change, balance_before=balance_before,
        balance_after=balance_after, created_by=actor.id if actor else None,
    )
    db.add(transaction)
    db.flush()
    enqueue_transaction(db, transaction, user, actor, replay=False)
    return transaction


def reconcile_outbox(db: Session) -> dict[str, int]:
    """Replay canonical member and ledger snapshots without creating duplicates."""
    registrations = transactions = 0
    for user in db.scalars(select(User).order_by(User.id)).all():
        enqueue_registration(db, user, replay=True)
        enqueue_member_update(db, user, "Reconciliation snapshot", replay=True)
        registrations += 1
    users = {user.id: user for user in db.scalars(select(User)).all()}
    for transaction in db.scalars(select(Transaction).order_by(Transaction.id)).all():
        user = users.get(transaction.user_id)
        if not user:
            continue
        actor = users.get(transaction.created_by) if transaction.created_by else None
        enqueue_transaction(db, transaction, user, actor, replay=True)
        transactions += 1
    return {"members": registrations, "transactions": transactions}


def signed_headers(secret: str, body: bytes, timestamp: int) -> dict[str, str]:
    signature = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Website-Timestamp": str(timestamp),
        "X-Website-Signature": f"sha256={signature}",
    }


async def deliver_event(settings: Settings, event: SheetSyncEvent) -> str:
    if not settings.delta_bot_internal_url or not settings.delta_bot_internal_secret:
        raise RuntimeError("Delta Main Bot sheet sync is not configured")
    if len(settings.delta_bot_internal_secret) < 32:
        raise RuntimeError("DELTA_BOT_INTERNAL_SECRET must contain at least 32 characters")
    parsed = urlparse(settings.delta_bot_internal_url)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("DELTA_BOT_INTERNAL_URL must use HTTPS")
    body = json.dumps({
        "event_id": event.id, "event_type": event.event_type,
        "occurred_at": _iso(event.created_at), "payload": event.payload,
    }, sort_keys=True, separators=(",", ":")).encode()
    timestamp = int(datetime.now(timezone.utc).timestamp())
    url = settings.delta_bot_internal_url.rstrip("/") + "/internal/website-sync"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, content=body, headers=signed_headers(settings.delta_bot_internal_secret, body, timestamp))
    if response.status_code == 409:
        logger.info("Sheet sync duplicate accepted event_id=%s", event.id)
        return "duplicate"
    response.raise_for_status()
    return "delivered"


async def process_outbox_once(settings: Settings, *, limit: int = 25) -> dict[str, int]:
    """Claim and deliver due events; website mutations have already committed."""
    if not settings.delta_bot_internal_url or not settings.delta_bot_internal_secret:
        return {"delivered": 0, "failed": 0}
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        # Make events claimable again after a worker dies mid-request.
        stale = db.scalars(select(SheetSyncEvent).where(
            SheetSyncEvent.status == "PROCESSING",
            SheetSyncEvent.locked_at < now - timedelta(minutes=5),
        )).all()
        for event in stale:
            event.status = "PENDING"; event.locked_at = None
            logger.warning("Sheet sync retry unlocked event_id=%s", event.id)
        db.commit()
        ids = list(db.scalars(select(SheetSyncEvent.id).where(
            SheetSyncEvent.status.in_(["PENDING", "FAILED"]),
            SheetSyncEvent.next_attempt_at <= now,
        ).order_by(SheetSyncEvent.created_at).limit(limit)).all())
    result = {"delivered": 0, "failed": 0}
    for event_id in ids:
        with SessionLocal() as db:
            event = db.get(SheetSyncEvent, event_id)
            if not event or event.status not in {"PENDING", "FAILED"}:
                continue
            event.status = "PROCESSING"; event.locked_at = now; event.attempts += 1
            db.commit(); db.refresh(event)
            attempt = event.attempts
            if attempt > 1:
                logger.info("Sheet sync entry retried event_id=%s attempt=%s", event_id, attempt)
        try:
            outcome = await deliver_event(settings, event)
        except Exception as exc:
            with SessionLocal() as db:
                stored = db.get(SheetSyncEvent, event_id)
                if stored:
                    stored.status = "FAILED"; stored.locked_at = None
                    stored.last_error = str(exc)[:2000]
                    stored.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=min(3600, 15 * (2 ** min(attempt - 1, 8))))
                    db.commit()
            logger.warning("Sheet sync failed event_id=%s attempt=%s error=%s", event_id, attempt, exc)
            result["failed"] += 1
        else:
            with SessionLocal() as db:
                stored = db.get(SheetSyncEvent, event_id)
                if stored:
                    stored.status = "DELIVERED"; stored.locked_at = None
                    stored.delivered_at = datetime.now(timezone.utc); stored.last_error = None
                    db.commit()
            logger.info("Sheet sync succeeded event_id=%s outcome=%s attempt=%s", event_id, outcome, attempt)
            result["delivered"] += 1
    return result
