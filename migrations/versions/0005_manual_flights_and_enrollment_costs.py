"""Add manual flight details, completion rewards, and Medallion costs."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tier_columns = {column["name"] for column in inspector.get_columns("tier_config")}
    if "enrollment_cost" not in tier_columns:
        with op.batch_alter_table("tier_config") as batch:
            batch.add_column(sa.Column("enrollment_cost", sa.BigInteger(), nullable=False, server_default="0"))
    flight_columns = {column["name"] for column in inspector.get_columns("flights")}
    with op.batch_alter_table("flights") as batch:
        if "flight_number" not in flight_columns: batch.add_column(sa.Column("flight_number", sa.String(20), nullable=False, server_default="DAL 0000"))
        if "departure_airport" not in flight_columns: batch.add_column(sa.Column("departure_airport", sa.String(8), nullable=False, server_default="TBA"))
        if "destination_airport" not in flight_columns: batch.add_column(sa.Column("destination_airport", sa.String(8), nullable=False, server_default="TBA"))
        if "miles_reward" not in flight_columns: batch.add_column(sa.Column("miles_reward", sa.BigInteger(), nullable=False, server_default="0"))
    costs = {"MEMBER": 0, "SILVER": 20000, "GOLD": 30000, "PLATINUM": 40000, "DIAMOND": 50000}
    for tier, cost in costs.items():
        op.get_bind().execute(sa.text("UPDATE tier_config SET enrollment_cost=:cost WHERE CAST(tier AS TEXT)=:tier"), {"cost":cost,"tier":tier})


def downgrade():
    with op.batch_alter_table("flights") as batch:
        batch.drop_column("miles_reward"); batch.drop_column("destination_airport"); batch.drop_column("departure_airport"); batch.drop_column("flight_number")
    with op.batch_alter_table("tier_config") as batch:
        batch.drop_column("enrollment_cost")
