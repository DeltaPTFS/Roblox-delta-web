"""Discord-only forms, submission tracking and crew flight fillouts."""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("flights", sa.Column("hosted_by_discord_id", sa.String(32), nullable=True))
    op.create_table(
        "community_forms",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(90), unique=True, nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("questions", sa.JSON, nullable=False),
        sa.Column("allowed_roles", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("is_flight_form", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_by_discord_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_community_forms_slug", "community_forms", ["slug"], unique=True)
    op.create_table(
        "community_form_responses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submission_key", sa.String(64), unique=True, nullable=False),
        sa.Column("form_id", sa.Integer, sa.ForeignKey("community_forms.id"), nullable=False),
        sa.Column("flight_id", sa.Integer, sa.ForeignKey("flights.id"), nullable=True),
        sa.Column("discord_user_id", sa.String(32), nullable=False),
        sa.Column("discord_display_name", sa.String(100), nullable=False),
        sa.Column("answers", sa.JSON, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_community_form_responses_form_id", "community_form_responses", ["form_id"])
    op.create_index("ix_community_form_responses_flight_id", "community_form_responses", ["flight_id"])
    op.create_index("ix_community_form_responses_discord_user_id", "community_form_responses", ["discord_user_id"])


def downgrade():
    op.drop_column("flights", "hosted_by_discord_id")
    op.drop_table("community_form_responses")
    op.drop_table("community_forms")
