"""Store staff-uploaded roleplay gallery media."""
from alembic import op
import sqlalchemy as sa
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "site_gallery_images",
        sa.Column("slug", sa.String(50), primary_key=True),
        sa.Column("mime_type", sa.String(24), nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

def downgrade():
    op.drop_table("site_gallery_images")
