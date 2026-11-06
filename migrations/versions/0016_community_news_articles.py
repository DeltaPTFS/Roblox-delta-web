"""Add owner-published long-form community news articles.

Run via alembic upgrade head in the database release job before enabling
the Vercel application version. Do not create tables in serverless startup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "community_news_articles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_community_news_published_updated", "community_news_articles", ["published", "updated_at"])


def downgrade():
    op.drop_index("ix_community_news_published_updated", table_name="community_news_articles")
    op.drop_table("community_news_articles")
