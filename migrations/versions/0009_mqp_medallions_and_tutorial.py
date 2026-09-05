"""Use MQP-only Medallion qualification and remember tutorial completion."""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "tutorial_completed_at" not in columns:
        op.add_column("users", sa.Column("tutorial_completed_at", sa.DateTime(timezone=True)))
        # Existing members can reopen the tutorial from their profile menu;
        # only memberships created after this migration are prompted automatically.
        op.execute("UPDATE users SET tutorial_completed_at = CURRENT_TIMESTAMP")
    thresholds = {"SILVER": 2500, "GOLD": 5000, "PLATINUM": 7500, "DIAMOND": 10000}
    for tier, mqp in thresholds.items():
        op.get_bind().execute(
            sa.text("UPDATE tier_config SET miles_threshold=0, mqp_threshold=:mqp, segments_threshold=0, enrollment_cost=0 WHERE CAST(tier AS TEXT)=:tier"),
            {"mqp": mqp, "tier": tier},
        )


def downgrade():
    # Tutorial completion is harmless historical preference data.
    pass
