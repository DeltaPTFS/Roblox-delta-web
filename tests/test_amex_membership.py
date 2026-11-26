from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from website.app.database import Base
from website.app.models import User, AuditLog, Transaction
from website.app.amex_membership import apply_card_action, dashboard_card
import pytest
from fastapi import HTTPException

def member(n):
    return User(roblox_user_id=str(n),roblox_username="pilot",roblox_display_name="Pilot",discord_user_id=str(n)*18,discord_username="pilot",discord_display_name="Pilot",skymiles_number="SM-"+str(n)*8)

def test_card_registration_purchase_and_fulfillment_are_idempotent():
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        actor,user=member(1),member(2)
        db.add_all([actor,user]);db.flush()
        def run(action,data,key):
            result=apply_card_action(db,user,actor,action,data,key,"Verified by leadership")
            db.commit()
            return result
        r=run("amex-register",{"tier":"reserve"},"100")
        assert r["balance"]==50000 and r["mqp"]==2500
        assert run("amex-register",{"tier":"reserve"},"101")["duplicate"]
        assert run("amex-register",{"tier":"reserve"},"100")["duplicate"]
        r=run("amex-purchase",{"robux":100,"category":"delta","reference":"verified-1"},"102")
        assert r["balance"]==50300 and r["mqp"]==2510
        with pytest.raises(HTTPException):
            run("amex-purchase",{"robux":100,"category":"delta","reference":"verified-1"},"103")
        run("amex-use",{"benefit":"welcome_comfort","reference":"flight-1"},"104")
        assert dashboard_card(db,user)["credits"]["welcome_comfort"]==1
        assert run("amex-use",{"benefit":"welcome_comfort","reference":"flight-1"},"104")["duplicate"]
        run("amex-revoke",{},"105")
        assert dashboard_card(db,user) is None
        with pytest.raises(HTTPException):run("amex-register",{"tier":"reserve"},"106")
        assert user.miles_balance==50300
        assert len(db.scalars(select(Transaction)).all())==2

def test_gold_offer_must_be_approved_and_capped():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine)
    with Session(engine) as db:
        actor,user=member(1),member(2);db.add_all([actor,user]);db.flush()
        with pytest.raises(HTTPException):apply_card_action(db,user,actor,"amex-register",{"tier":"gold","welcome_miles":80001},"100","test")
        r=apply_card_action(db,user,actor,"amex-register",{"tier":"gold","welcome_miles":65000},"101","test")
        assert r["balance"]==65000 and r["card"]["credits"]["comfort_first"]==1
