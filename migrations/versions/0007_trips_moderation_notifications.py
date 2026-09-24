"""Add complete trips, moderation and notification delivery history."""
from alembic import op
import sqlalchemy as sa

revision="0007"
down_revision="0006"
branch_labels=None
depends_on=None


def _add_missing(table, columns):
    existing={column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    with op.batch_alter_table(table) as batch:
        for column in columns:
            if column.name not in existing: batch.add_column(column)


def upgrade():
    _add_missing("users",[sa.Column("restriction_reason",sa.Text()),sa.Column("restricted_until",sa.DateTime(timezone=True)),sa.Column("permanent_ban",sa.Boolean(),nullable=False,server_default=sa.false())])
    _add_missing("flights",[sa.Column("aircraft",sa.String(100)),sa.Column("gate",sa.String(30))])
    _add_missing("bookings",[sa.Column("confirmation_number",sa.String(20)),sa.Column("seat",sa.String(20)),sa.Column("cabin",sa.String(40)),sa.Column("carry_on",sa.String(80)),sa.Column("checked_bags",sa.String(80)),sa.Column("miles_used",sa.BigInteger(),nullable=False,server_default="0"),sa.Column("miles_refunded",sa.BigInteger(),nullable=False,server_default="0"),sa.Column("cancelled_at",sa.DateTime(timezone=True)),sa.Column("attendance_status",sa.String(30),nullable=False,server_default="PENDING")])
    bind=op.get_bind(); inspector=sa.inspect(bind); booking_columns={c["name"] for c in inspector.get_columns("bookings")}
    if "confirmation_number" in booking_columns:
        bind.execute(sa.text("UPDATE bookings SET confirmation_number = 'DL-' || id WHERE confirmation_number IS NULL"))
        indexes={index["name"] for index in inspector.get_indexes("bookings")}
        if "ix_bookings_confirmation_number" not in indexes: op.create_index("ix_bookings_confirmation_number","bookings",["confirmation_number"],unique=True)
    tables=set(inspector.get_table_names())
    if "moderation_actions" not in tables:
        op.create_table("moderation_actions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("moderator_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("flight_id",sa.Integer(),sa.ForeignKey("flights.id")),sa.Column("action",sa.String(40),nullable=False),sa.Column("reason",sa.Text(),nullable=False),sa.Column("reversed_at",sa.DateTime(timezone=True)),sa.Column("reversed_by",sa.Integer(),sa.ForeignKey("users.id")),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
        op.create_index("ix_moderation_actions_user_id","moderation_actions",["user_id"]);op.create_index("ix_moderation_actions_created_at","moderation_actions",["created_at"])
    if "notification_logs" not in tables:
        op.create_table("notification_logs",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("flight_id",sa.Integer(),sa.ForeignKey("flights.id")),sa.Column("booking_id",sa.Integer(),sa.ForeignKey("bookings.id")),sa.Column("notification_type",sa.String(50),nullable=False),sa.Column("event_key",sa.String(160),nullable=False,unique=True),sa.Column("delivery_status",sa.String(30),nullable=False),sa.Column("error",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
        op.create_index("ix_notification_logs_user_id","notification_logs",["user_id"]);op.create_index("ix_notification_logs_created_at","notification_logs",["created_at"])


def downgrade():
    # History-bearing tables/columns are intentionally retained on downgrade to avoid deleting moderation and notification evidence.
    pass
