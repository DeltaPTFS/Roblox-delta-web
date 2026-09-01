"""Initial SkyMiles schema."""
from alembic import op
from website.app.database import Base
from website.app import models
revision="0001"; down_revision=None; branch_labels=None; depends_on=None
def upgrade(): Base.metadata.create_all(bind=op.get_bind())
def downgrade(): Base.metadata.drop_all(bind=op.get_bind())
