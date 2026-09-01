"""Add Discord event flights and member bookings."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "flights" not in tables:
        op.create_table(
            "flights",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("discord_event_id", sa.String(32), nullable=False, unique=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("location", sa.String(160), nullable=False, server_default="To be announced"),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True)),
            sa.Column("image_url", sa.Text()),
            sa.Column("status", sa.Enum("SCHEDULED", "DELAYED", "CANCELLED", "COMPLETED", name="flightstatus"), nullable=False, server_default="SCHEDULED"),
            sa.Column("status_message", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_flights_discord_event_id", "flights", ["discord_event_id"], unique=True)
        op.create_index("ix_flights_starts_at", "flights", ["starts_at"])
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "bookings" not in tables:
        op.create_table(
            "bookings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("flight_id", sa.Integer(), sa.ForeignKey("flights.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("amenities", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(30), nullable=False, server_default="CONFIRMED"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("flight_id", "user_id", name="uq_booking_flight_user"),
        )
        op.create_index("ix_bookings_flight_id", "bookings", ["flight_id"])
        op.create_index("ix_bookings_user_id", "bookings", ["user_id"])


def downgrade():
    op.drop_table("bookings")
    op.drop_table("flights")
    sa.Enum(name="flightstatus").drop(op.get_bind(), checkfirst=True)
