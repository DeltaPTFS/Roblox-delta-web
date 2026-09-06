"""Persist member themes and feedback."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "theme_preference" not in user_columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("theme_preference", sa.String(10), nullable=False, server_default="system"))
    if "feedback" not in inspector.get_table_names():
        op.create_table(
            "feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("website_rating", sa.Integer(), nullable=False),
            sa.Column("community_rating", sa.Integer(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("website_rating BETWEEN 1 AND 5", name="ck_feedback_website_rating"),
            sa.CheckConstraint("community_rating BETWEEN 1 AND 5", name="ck_feedback_community_rating"),
        )
        op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
        op.create_index("ix_feedback_created_at", "feedback", ["created_at"])


def downgrade():
    op.drop_table("feedback")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("theme_preference")
