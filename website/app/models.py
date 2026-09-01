import enum
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def now(): return datetime.now(timezone.utc)


class Status(str, enum.Enum): ACTIVE="ACTIVE"; SUSPENDED="SUSPENDED"; DISABLED="DISABLED"
class Tier(str, enum.Enum): MEMBER="SKYMILES MEMBER"; SILVER="SILVER MEDALLION"; GOLD="GOLD MEDALLION"; PLATINUM="PLATINUM MEDALLION"; DIAMOND="DIAMOND MEDALLION"
class FlightStatus(str, enum.Enum): SCHEDULED="SCHEDULED"; DELAYED="DELAYED"; CANCELLED="CANCELLED"; COMPLETED="COMPLETED"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    roblox_user_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    roblox_username: Mapped[str] = mapped_column(String(64))
    roblox_display_name: Mapped[str] = mapped_column(String(64))
    roblox_avatar_url: Mapped[str | None] = mapped_column(Text)
    roblox_group_role: Mapped[str | None] = mapped_column(String(100))
    roblox_group_rank: Mapped[int] = mapped_column(Integer, default=0)
    discord_user_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    discord_username: Mapped[str] = mapped_column(String(64))
    discord_display_name: Mapped[str] = mapped_column(String(64))
    discord_avatar_url: Mapped[str | None] = mapped_column(Text)
    discord_role_ids: Mapped[list] = mapped_column(JSON, default=list)
    skymiles_number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    miles_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    lifetime_miles: Mapped[int] = mapped_column(BigInteger, default=0)
    medallion_qualifying_points: Mapped[int] = mapped_column(BigInteger, default=0)
    segments_flown: Mapped[int] = mapped_column(Integer, default=0)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), default=Tier.MEMBER)
    medallion_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    account_status: Mapped[Status] = mapped_column(Enum(Status), default=Status.ACTIVE)
    roblox_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    discord_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class TierConfig(Base):
    __tablename__ = "tier_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), unique=True)
    miles_threshold: Mapped[int] = mapped_column(BigInteger)
    mqp_threshold: Mapped[int] = mapped_column(BigInteger, default=0)
    segments_threshold: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    benefits: Mapped[list] = mapped_column(JSON, default=list)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(255))
    reference: Mapped[str | None] = mapped_column(String(100))
    miles_change: Mapped[int] = mapped_column(BigInteger)
    balance_before: Mapped[int] = mapped_column(BigInteger)
    balance_after: Mapped[int] = mapped_column(BigInteger)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Reward(Base):
    __tablename__ = "rewards"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    miles_cost: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Redemption(Base):
    __tablename__ = "redemptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reward_id: Mapped[int] = mapped_column(ForeignKey("rewards.id"))
    miles_cost: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(30), default="FULFILMENT_PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    security_metadata: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebSession(Base):
    __tablename__ = "web_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Flight(Base):
    __tablename__ = "flights"
    id: Mapped[int] = mapped_column(primary_key=True)
    discord_event_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(160), default="To be announced")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    image_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FlightStatus] = mapped_column(Enum(FlightStatus), default=FlightStatus.SCHEDULED)
    status_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amenities: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="CONFIRMED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    __table_args__ = (
        UniqueConstraint("flight_id", "user_id", name="uq_booking_flight_user"),
    )
