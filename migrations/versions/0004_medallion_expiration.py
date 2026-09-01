"""Add annual Medallion expiration timestamp."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "medallion_expires_at" not in columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("medallion_expires_at", sa.DateTime(timezone=True)))
            batch.create_index("ix_users_medallion_expires_at", ["medallion_expires_at"])
    eastern_now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    expiration = datetime(eastern_now.year + 1, 1, 1, tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    op.get_bind().execute(
        sa.text("UPDATE users SET medallion_expires_at = :expiration WHERE CAST(tier AS TEXT) != 'MEMBER' AND medallion_expires_at IS NULL"),
        {"expiration": expiration},
    )


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_medallion_expires_at")
        batch.drop_column("medallion_expires_at")
