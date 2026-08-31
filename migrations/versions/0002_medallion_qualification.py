"""Add configurable Medallion miles, MQP, segment, and benefit criteria."""
import json

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with op.batch_alter_table("users") as batch:
        if "medallion_qualifying_points" not in user_columns:
            batch.add_column(sa.Column("medallion_qualifying_points", sa.BigInteger(), nullable=False, server_default="0"))
        if "segments_flown" not in user_columns:
            batch.add_column(sa.Column("segments_flown", sa.Integer(), nullable=False, server_default="0"))

    tier_columns = {column["name"] for column in inspector.get_columns("tier_config")}
    with op.batch_alter_table("tier_config") as batch:
        if "threshold" in tier_columns and "miles_threshold" not in tier_columns:
            batch.alter_column("threshold", new_column_name="miles_threshold")
        if "mqp_threshold" not in tier_columns:
            batch.add_column(sa.Column("mqp_threshold", sa.BigInteger(), nullable=False, server_default="0"))
        if "segments_threshold" not in tier_columns:
            batch.add_column(sa.Column("segments_threshold", sa.Integer(), nullable=False, server_default="0"))
        if "description" not in tier_columns:
            batch.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        if "benefits" not in tier_columns:
            batch.add_column(sa.Column("benefits", sa.JSON(), nullable=False, server_default="[]"))

    requirements = {
        "MEMBER": (0, 0, 0, "Start earning toward Medallion Status with every eligible community journey.", ["Earn and redeem SkyMiles", "Member rewards catalog"]),
        "SILVER": (20000, 4000, 1, "The stepping stone to Medallion Status, with elevated recognition on eligible community trips.", ["Complimentary upgrade eligibility", "Priority boarding"]),
        "GOLD": (30000, 12000, 5, "Unlock a broader suite of priority services and recognition throughout the community.", ["Unlimited complimentary upgrade eligibility", "Sky Priority-style community services"]),
        "PLATINUM": (40000, 20000, 10, "The final step before Diamond, with customizable benefits and premium community recognition.", ["Unlimited complimentary upgrade eligibility", "Choice Benefits", "Priority services"]),
        "DIAMOND": (50000, 28000, 15, "Our highest roleplay Medallion tier, recognizing the community's most engaged travelers.", ["Highest upgrade priority", "Highest Medallion boarding priority", "Customizable Choice Benefits"]),
    }
    benefits_expression = "CAST(:benefits AS JSON)" if bind.dialect.name == "postgresql" else ":benefits"
    for tier, values in requirements.items():
        # PostgreSQL enum columns cannot be compared directly with a VARCHAR
        # bind parameter. Cast the enum to text so this migration works on
        # both PostgreSQL and SQLite instead of raising SQLAlchemy f405.
        bind.execute(
            sa.text(
                f"""
                UPDATE tier_config
                SET miles_threshold = :miles,
                    mqp_threshold = :mqp,
                    segments_threshold = :segments,
                    description = :description,
                    benefits = {benefits_expression}
                WHERE CAST(tier AS TEXT) = :tier
                """
            ),
            {
                "tier": tier,
                "miles": values[0],
                "mqp": values[1],
                "segments": values[2],
                "description": values[3],
                "benefits": json.dumps(values[4]),
            },
        )


def downgrade():
    with op.batch_alter_table("tier_config") as batch:
        batch.drop_column("benefits")
        batch.drop_column("description")
        batch.drop_column("segments_threshold")
        batch.drop_column("mqp_threshold")
        batch.alter_column("miles_threshold", new_column_name="threshold")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("segments_flown")
        batch.drop_column("medallion_qualifying_points")
