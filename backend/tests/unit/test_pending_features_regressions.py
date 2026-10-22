"""Regression checks for the six pending features; no live detections fabricated."""
import pytest
from app.core.config import settings
from ai_engine.behavioral.campus_events import CampusEvents
from ai_engine.behavioral.fall import FallDetector
from ai_engine.vision.vehicle_counter import VehicleCounter
from ai_engine.behavioral.crowd import CrowdAnalyzer
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions
from ai_engine.vision.behavior_overlay import event, BehaviorOverlayCache

def track(tid=1, x=.5, kind='person'):
    return dict(track_id=tid,class_name=kind,bbox=[x*1000-50,300,x*1000+50,700],cx=x*1000,cy=500,confidence=.9,time_since_update=0)

def test_bag_old_owner_clears_on_ambiguous_reassociation(monkeypatch):
    monkeypatch.setattr(settings,'ACTIVITY_DEBUG',False)
    a=CampusEvents(settings);bag=track(9,.5,'backpack')
    a.analyze([bag,track(1,.5)],{},(1000,1000),now=0)
    assert a.bags[9]['owner']==1
    a.analyze([bag,track(1,.49),track(2,.51)],{},(1000,1000),now=1)
    assert a.bags[9]['owner'] is None
    for now in range(2,60):
        assert not a.analyze([bag],{},(1000,1000),now=now)

def test_bag_reappearing_after_grace_requires_new_owner(monkeypatch):
    monkeypatch.setattr(settings,'ACTIVITY_DEBUG',False)
    a=CampusEvents(settings);bag=track(9,.5,'suitcase')
    a.analyze([bag,track()],{},(1000,1000),now=0)
    a.analyze([bag],{},(1000,1000),now=1)
    a.analyze([],{},(1000,1000),now=2)
    a.analyze([bag],{},(1000,1000),now=5)
    assert a.bags[9]['owner'] is None
    assert 'unattended_since' not in a.bags[9]

def test_fall_candidate_does_not_bridge_unobserved_track_gap():
    d=FallDetector(settings)
    upright=track(); horizontal={**track(),'bbox':[100,500,700,800]}
    pose={'left_shoulder':(.4,.2),'right_shoulder':(.6,.2),'left_hip':(.4,.7),'right_hip':(.6,.7)}
    down={'left_shoulder':(.2,.45),'right_shoulder':(.2,.55),'left_hip':(.8,.45),'right_hip':(.8,.55)}
    d.analyze([upright],{1:{'fall_pose':pose}},(1000,1000),now=0)
    d.analyze([horizontal],{1:{'fall_pose':down}},(1000,1000),now=1)
    assert d.states[1]['phase']=='FALL CANDIDATE'
    assert not d.analyze([horizontal],{1:{'fall_pose':down}},(1000,1000),now=5)
    assert d.states[1]['phase']=='NORMAL'

def test_vehicle_invalid_box_cannot_create_crossing():
    c=VehicleCounter();c.configure({'enabled':True,'points':[{'x':0,'y':.5},{'x':1,'y':.5}]})
    v=track(kind='car');v['bbox']=[100,200,200,300]
    c.update([v],(1000,1000))
    v['bbox']=[100,float('nan'),200,800]
    assert c.update([v],(1000,1000))['total']==0
    v['bbox']=[100,700,200,800]
    assert c.update([v],(1000,1000))['total']==0

@pytest.mark.parametrize('kind,severity,tid', [('suspected_fight','high',None),('abandoned_bag','high',None),('fall_detected','high',1),('loitering','medium',1),('crowd_surge','high',None)])
def test_confirmed_overlay_and_existing_alert_router_emit_once(kind,severity,tid):
    cache=BehaviorOverlayCache('test');router=ConfirmedAlertTransitions();people=[track()]
    e=event(kind,severity,tid,track_ids=[1,2])
    cache.update('pending',{'stream_session':'test','observed_at':100,'overlay_events':[e]},now=100)
    enriched,banners=cache.attach(people,now=100)
    if tid is None:assert banners[0]['type']==kind and not enriched[0]['behaviors']
    else:assert not banners and enriched[0]['behaviors'][0]['track_id']==1
    assert len(router.update([e],people,now=0))==1
    for now in (1,2,3,4):assert not router.update([e],people,now=now)
    router.update([],people,now=8)
    assert len(router.update([e],people,now=9))==1

def test_surge_stale_and_duplicate_ids_cannot_supply_growth():
    a=CrowdAnalyzer('regression')
    baseline=[track(i,x=.05+i*.1) for i in range(6)]
    for now in range(6):a.analyze(baseline,now=now)
    extras=[{**track(i+10),'time_since_update':1} for i in range(10)]
    for now in range(6,16):
        alerts=a.analyze(baseline+baseline+extras,now=now)
        assert not any(e['alert_type']=='crowd_surge' for e in alerts)

