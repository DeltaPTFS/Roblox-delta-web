"""Add persistent top-of-site announcement controlled by Ownership."""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "site_announcements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("message", sa.String(220), nullable=False, server_default=""),
        sa.Column("tone", sa.String(20), nullable=False, server_default="UPDATE"),
        sa.Column("link_label", sa.String(32), nullable=False, server_default=""),
        sa.Column("link_path", sa.String(255), nullable=False, server_default=""),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("site_announcements")
