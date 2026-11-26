"""Virtual card membership state, serialized by the existing locked User row.
Audit snapshots retain registration, benefit usage and purchase history without a schema migration.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from .models import AuditLog, Status
from .sheet_sync import add_transaction, enqueue_member_update

POLICIES = {
    "blue": {"name":"Blue","fee":0,"welcome":10000,"rates":{"delta":2,"partner":2,"other":1},"perks":[],"credits":{}},
    "gold": {"name":"Gold","fee":500,"welcome":80000,"rates":{"delta":2,"partner":2,"other":1},"perks":["Zone 5 priority boarding"],"credits":{"comfort_first":1,"first_second":1}},
    "platinum": {"name":"Platinum","fee":1000,"welcome":0,"rates":{},"perks":[],"credits":{}},
    "reserve": {"name":"Reserve","fee":2000,"welcome":50000,"rates":{"delta":3,"partner":1,"other":1},"perks":["Zone 5 priority boarding","Virtual Sky Club when flying Delta","Virtual partner lounge access subject to partner rules","Complimentary upgrade list subject to availability"],"credits":{"comfort_first":1,"first_second":1,"welcome_comfort":2,"guest_pass":1,"security_credit":1}},
}
LABELS = {"comfort_first":"First Delta flight: Comfort Plus upgrade","first_second":"Second Delta flight: First Class upgrade","welcome_comfort":"Welcome offer Comfort Plus upgrades","guest_pass":"Virtual Sky Club guest pass (travel together on Delta)","security_credit":"Virtual Global Entry / TSA PreCheck credit"}
STATE_ACTION = "AMEX_CARD_STATE"

def state_for(db, user):
    row=db.scalar(select(AuditLog).where(AuditLog.target_user_id==user.id,AuditLog.action==STATE_ACTION).order_by(AuditLog.id.desc()).limit(1))
    return deepcopy(row.new_value) if row else None

def dashboard_card(db,user):
    state=state_for(db,user)
    if not state or not state.get("active"): return None
    policy=POLICIES[state["tier"]]
    return {**state,"name":policy["name"],"fee":policy["fee"],"rates":policy["rates"],"perks":policy["perks"],"credits_display":[{"label":LABELS[k],"remaining":v} for k,v in state["credits"].items()]}

def fail(message, status=422):
    raise HTTPException(status,message)

def whole(value, minimum, maximum):
    if type(value) is not int or not minimum<=value<=maximum: fail(f"Enter a whole number between {minimum} and {maximum}")
    return value

def apply_card_action(db,user,actor,action,data,interaction_id,reason):
    old=state_for(db,user)
    if action=="amex-status":
        return {"card":dashboard_card(db,user),"balance":user.miles_balance,"mqp":user.medallion_qualifying_points}
    # Every action uses one immutable audit record keyed by the Discord interaction.
    audits=db.scalars(select(AuditLog).where(AuditLog.target_user_id==user.id,AuditLog.action==STATE_ACTION).order_by(AuditLog.id)).all()
    if any((a.security_metadata or {}).get("discord_interaction_id")==interaction_id for a in audits):
        return {"duplicate":True,"card":dashboard_card(db,user),"balance":user.miles_balance,"mqp":user.medallion_qualifying_points}
    state=deepcopy(old) if old else {}
    credit=0
    mqp=0
    reference=str(data.get("reference") or "").strip()[:100]
    year=datetime.now(timezone.utc).year
    if action=="amex-register":
        tier=str(data.get("tier") or "").lower()
        if tier not in POLICIES: fail("Choose Blue, Gold, Platinum or Reserve")
        if state.get("active"):
            if state["tier"]==tier: return {"duplicate":True,"card":dashboard_card(db,user),"balance":user.miles_balance,"mqp":user.medallion_qualifying_points}
            fail("Revoke the existing card before registering a different tier",409)
        previous=next((a.new_value for a in reversed(audits) if (a.new_value or {}).get("tier")==tier),None)
        if previous: fail("This tier was already registered; contact Ownership for a manual review before reactivation",409)
        policy=POLICIES[tier]
        credit=whole(data.get("welcome_miles"),0,80000) if tier=="gold" else policy["welcome"]
        if tier!="gold" and data.get("welcome_miles") not in (None,credit): fail("Welcome amount is fixed for this tier")
        state={"tier":tier,"active":True,"registered_at":datetime.now(timezone.utc).isoformat(),"credits":dict(policy["credits"]),"welcome_miles":credit,"headstart_year":year if tier=="reserve" else None}
        if tier=="reserve": mqp=2500
    elif action=="amex-revoke":
        if not state.get("active"): fail("No active card",409)
        state["active"]=False
    elif action=="amex-use":
        if not state.get("active"): fail("No active card",409)
        benefit=str(data.get("benefit") or "")
        if state["credits"].get(benefit,0)<=0: fail("No remaining entitlement for this benefit",409)
        if not reference: fail("Provide an eligible flight or fulfillment reference")
        if any((a.security_metadata or {}).get("benefit")==benefit and (a.security_metadata or {}).get("reference")==reference for a in audits): fail("This benefit reference was already recorded",409)
        state["credits"][benefit]-=1
    elif action=="amex-purchase":
        if not state.get("active"): fail("No active card",409)
        if not reference: fail("A unique verified purchase reference is required")
        if any((a.security_metadata or {}).get("purchase_reference")==reference for a in audits): fail("Purchase already recorded",409)
        amount=whole(data.get("robux"),1,100000)
        category=str(data.get("category") or "")
        rates=POLICIES[state["tier"]]["rates"]
        if category not in rates: fail("This earning rate is not confirmed for the card")
        credit=amount*rates[category]
        if state["tier"]=="reserve": mqp=amount//10
    elif action=="amex-renew":
        if not state.get("active") or state["tier"]!="reserve": fail("Only active Reserve cards have confirmed annual headstart benefits")
        if state.get("headstart_year")==year: fail("This year's headstart has already been awarded",409)
        state["headstart_year"]=year
        state["credits"]["guest_pass"]=1
        mqp=2500
    else: fail("Unknown card action",404)
    before=user.miles_balance
    user.miles_balance+=credit
    user.lifetime_miles+=credit
    user.medallion_qualifying_points+=mqp
    if credit:
        add_transaction(db,user,type="AMEX_WELCOME" if action=="amex-register" else "AMEX_PURCHASE",description=("AMEX "+action.removeprefix("amex-")+": "+reason)[:255],reference="amex:"+interaction_id,miles_change=credit,balance_before=before,balance_after=user.miles_balance,actor=actor)
    elif mqp: enqueue_member_update(db,user,"AMEX qualifying points",actor)
    meta={"discord_interaction_id":interaction_id,"operation":action,"reference":reference,"miles_awarded":credit,"mqp_awarded":mqp}
    if action=="amex-use": meta["benefit"]=benefit
    if action=="amex-purchase": meta["purchase_reference"]=reference
    db.add(AuditLog(staff_user_id=actor.id,target_user_id=user.id,action=STATE_ACTION,old_value=old,new_value=state,reason=reason,security_metadata=meta))
    db.flush()
    return {"duplicate":False,"card":dashboard_card(db,user),"balance":user.miles_balance,"mqp":user.medallion_qualifying_points,"miles_awarded":credit,"mqp_awarded":mqp}
