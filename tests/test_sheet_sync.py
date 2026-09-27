import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from website.app.config import Settings
from website.app.database import Base
from website.app.models import SheetSyncEvent, Status, Tier, User
from website.app import sheet_sync


def member(number="SM-10000001"):
    return User(
        roblox_user_id="123456", roblox_username="pilot", roblox_display_name="Captain Pilot",
        discord_user_id="1538738611988467782", discord_username="pilot.user",
        discord_display_name="Pilot", skymiles_number=number, miles_balance=0,
        lifetime_miles=0, medallion_qualifying_points=0, segments_flown=0,
        tier=Tier.MEMBER, account_status=Status.ACTIVE,
    )


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'sync.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(sheet_sync, "SessionLocal", factory)
    return factory


def test_website_registration_event_is_stable_and_duplicate_safe(isolated_db):
    with isolated_db() as db:
        user = member(); db.add(user); db.flush()
        first = sheet_sync.enqueue_registration(db, user)
        second = sheet_sync.enqueue_registration(db, user)
        assert first.id == second.id
        assert first.payload["source"] == "Website"
        assert first.payload["skymiles_number"] == user.skymiles_number
        db.commit()
    with isolated_db() as db:
        assert len(db.scalars(select(SheetSyncEvent)).all()) == 1


def test_mileage_increase_deduction_and_balance_after_are_mirrored(isolated_db):
    with isolated_db() as db:
        user = member(); db.add(user); db.flush()
        user.miles_balance = 500
        credit = sheet_sync.add_transaction(db, user, type="MILES_ADDED", description="Community event", reference="EVENT-1", miles_change=500, balance_before=0, balance_after=500, actor=user)
        user.miles_balance = 300
        debit = sheet_sync.add_transaction(db, user, type="MILES_DEDUCTED", description="Correction", reference="CORRECTION-1", miles_change=-200, balance_before=500, balance_after=300, actor=user)
        db.commit()
        events = db.scalars(select(SheetSyncEvent).where(SheetSyncEvent.event_type == "record_transaction").order_by(SheetSyncEvent.created_at)).all()
        assert [event.payload["miles_change"] for event in events] == [500, -200]
        assert [event.payload["balance_after"] for event in events] == [500, 300]
        assert events[0].event_key == f"transaction:{credit.id}"
        assert events[1].event_key == f"transaction:{debit.id}"


def test_tier_and_membership_update_are_snapshotted(isolated_db):
    with isolated_db() as db:
        user = member(); db.add(user); db.flush()
        user.tier = Tier.GOLD; user.account_status = Status.SUSPENDED
        event = sheet_sync.enqueue_member_update(db, user, "Tier and status update", user)
        db.commit()
        assert event.event_type == "update_member"
        assert event.payload["membership_tier"] == Tier.GOLD.value
        assert event.payload["registration_status"] == Status.SUSPENDED.value


def test_failed_sheet_sync_is_retried_without_changing_member(isolated_db, monkeypatch):
    with isolated_db() as db:
        user = member(); user.miles_balance = 750; db.add(user); db.flush()
        sheet_sync.enqueue_registration(db, user); db.commit(); user_id = user.id

    async def fail(*_):
        raise RuntimeError("Sheets unavailable")
    monkeypatch.setattr(sheet_sync, "deliver_event", fail)
    settings = Settings(delta_bot_internal_url="https://bot.example", delta_bot_internal_secret="x" * 48)
    result = asyncio.run(sheet_sync.process_outbox_once(settings))
    assert result == {"delivered": 0, "failed": 1}
    with isolated_db() as db:
        event = db.scalar(select(SheetSyncEvent)); assert event.status == "FAILED" and event.attempts == 1
        assert db.get(User, user_id).miles_balance == 750
        event.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()

    calls = []
    async def succeed(_, event):
        calls.append(event.id); return "delivered"
    monkeypatch.setattr(sheet_sync, "deliver_event", succeed)
    result = asyncio.run(sheet_sync.process_outbox_once(settings))
    assert result == {"delivered": 1, "failed": 0} and len(calls) == 1
    with isolated_db() as db:
        event = db.scalar(select(SheetSyncEvent)); assert event.status == "DELIVERED" and event.attempts == 2


def test_reconciliation_replays_members_and_transactions_without_new_ids(isolated_db):
    with isolated_db() as db:
        user = member(); db.add(user); db.flush()
        registration = sheet_sync.enqueue_registration(db, user)
        user.miles_balance = 150
        transaction = sheet_sync.add_transaction(db, user, type="WELCOME_BONUS", description="Welcome bonus", reference="WEBSITE-REGISTRATION", miles_change=150, balance_before=0, balance_after=150, actor=user)
        db.commit(); original_ids = {registration.id, sheet_sync.stable_event_id(f"transaction:{transaction.id}")}
        for event in db.scalars(select(SheetSyncEvent)).all(): event.status = "DELIVERED"
        db.commit()
        counts = sheet_sync.reconcile_outbox(db); db.commit()
        assert counts == {"members": 1, "transactions": 1}
        events = db.scalars(select(SheetSyncEvent)).all()
        assert original_ids.issubset({event.id for event in events})
        assert len({event.event_key for event in events}) == len(events)
        assert all(event.status == "PENDING" for event in events)


def test_bot_and_apps_script_packages_extend_existing_bridge():
    from pathlib import Path
    handler = Path("integrations/deltaptfs-bot/src/website-sync.js").read_text()
    adapter = Path("integrations/deltaptfs-bot/src/sheets-website-sync.js").read_text()
    script = Path("integrations/deltaptfs-bot/integrations/google-apps-script-extension.gs").read_text()
    assert "WEBSITE_SYNC_SECRET" in handler and "timingSafeEqual" in handler
    assert "GOOGLE_SHEETS_WEBHOOK_URL" not in handler  # Existing src/sheets.js owns this credential.
    assert "createSheetWebsiteSync" in adapter and "event.event_id" in adapter
    assert "Registration Logs" in script and "Mileage Ledger" in script
    assert "Website Transaction ID" in script and "handleWebsiteAction_" in script
    assert "function doPost" not in script  # Merge into the existing authenticated Apps Script handler.
