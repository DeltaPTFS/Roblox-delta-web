"""Add Roblox game destinations for flight boarding passes."""
from alembic import op
import sqlalchemy as sa

revision="0008"
down_revision="0007"
branch_labels=None
depends_on=None


def upgrade():
    columns={column["name"] for column in sa.inspect(op.get_bind()).get_columns("flights")}
    if "roblox_game_url" not in columns:
        op.add_column("flights",sa.Column("roblox_game_url",sa.Text(),nullable=True))


def downgrade():
    op.drop_column("flights","roblox_game_url")
