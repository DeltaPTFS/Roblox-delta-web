"""Add a durable outbox for Delta Main Bot / Google Sheets mirroring."""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    if "sheet_sync_events" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "sheet_sync_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_key", sa.String(180), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_key", name="uq_sheet_sync_events_event_key"),
    )
    op.create_index("ix_sheet_sync_events_event_key", "sheet_sync_events", ["event_key"], unique=True)
    op.create_index("ix_sheet_sync_events_event_type", "sheet_sync_events", ["event_type"])
    op.create_index("ix_sheet_sync_events_status", "sheet_sync_events", ["status"])
    op.create_index("ix_sheet_sync_events_next_attempt_at", "sheet_sync_events", ["next_attempt_at"])
    op.create_index("ix_sheet_sync_events_created_at", "sheet_sync_events", ["created_at"])


def downgrade():
    # Retain synchronization history during rollback so events are not replayed
    # blindly and auditability is not lost.
    pass
