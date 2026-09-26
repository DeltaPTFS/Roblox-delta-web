"""Seed required tier and reward defaults outside application startup."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    tiers = sa.Table("tier_config", metadata, autoload_with=bind)
    rewards = sa.Table("rewards", metadata, autoload_with=bind)

    existing_tiers = {str(value) for value in bind.execute(sa.select(tiers.c.tier)).scalars()}
    defaults = [
        ("MEMBER", 0, "Start earning toward Medallion Status with every eligible community journey.", ["Earn and redeem SkyMiles", "Member rewards catalog"]),
        ("SILVER", 2500, "The stepping stone to Medallion Status, with elevated recognition on eligible community trips.", ["Complimentary upgrade eligibility", "Priority boarding"]),
        ("GOLD", 5000, "Unlock a broader suite of priority services and recognition throughout the community.", ["Unlimited complimentary upgrade eligibility", "Sky Priority-style community services"]),
        ("PLATINUM", 7500, "The final step before Diamond, with customizable benefits and premium community recognition.", ["Unlimited complimentary upgrade eligibility", "Choice Benefits", "Priority services"]),
        ("DIAMOND", 10000, "Our highest roleplay Medallion tier, recognizing the community's most engaged travelers.", ["Highest upgrade priority", "Highest Medallion boarding priority", "Customizable Choice Benefits"]),
    ]
    for tier, mqp, description, benefits in defaults:
        if tier not in existing_tiers:
            bind.execute(tiers.insert().values(tier=tier, miles_threshold=0, mqp_threshold=mqp, segments_threshold=0, description=description, benefits=benefits, enrollment_cost=0))

    existing_rewards = {str(value) for value in bind.execute(sa.select(rewards.c.name)).scalars()}
    now = datetime.now(timezone.utc)
    for name, description, cost in [
        ("Priority Boarding", "Board first at a community flight.", 2500),
        ("Flight Upgrade", "Upgrade an eligible roleplay itinerary.", 5000),
        ("Exclusive Discord Role", "Unlock a distinguished community role.", 10000),
        ("Special Aircraft Access", "Access a featured community aircraft.", 15000),
    ]:
        if name not in existing_rewards:
            bind.execute(rewards.insert().values(name=name, description=description, image_url=None, miles_cost=cost, quantity=None, active=True, created_at=now, updated_at=now))


def downgrade():
    # Defaults may be referenced by production users and redemptions, so a
    # rollback intentionally retains them.
    pass
