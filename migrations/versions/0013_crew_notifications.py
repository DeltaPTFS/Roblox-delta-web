"""Add durable website-to-crew announcement outbox."""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crew_delivery_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_key", sa.String(180), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crew_delivery_events_event_key", "crew_delivery_events", ["event_key"], unique=True)
    op.create_index("ix_crew_delivery_events_kind", "crew_delivery_events", ["kind"])
    op.create_index("ix_crew_delivery_events_status", "crew_delivery_events", ["status"])


def downgrade():
    op.drop_table("crew_delivery_events")
