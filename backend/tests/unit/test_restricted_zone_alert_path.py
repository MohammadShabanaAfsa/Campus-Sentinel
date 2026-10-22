from unittest.mock import Mock
from datetime import datetime,timezone
import uuid,json
import pytest
from ai_engine.behavioral.zone_checker import ZoneChecker
from ai_engine.vision.behavior_overlay import BehaviorOverlayCache
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions

POINTS=[{'x':.1,'y':.6},{'x':.4,'y':.6},{'x':.4,'y':.9},{'x':.1,'y':.9}]

def checker(monkeypatch,camera='entrance',polygon_camera='entrance'):
    monkeypatch.setattr(ZoneChecker,'_load_zones',lambda self:None)
    obj=ZoneChecker(camera);obj._zones=[{'id':'zone','camera_id':polygon_camera,'name':'Restricted Area','points':POINTS,'alert_level':'high'}]
    return obj

def person(inside=True,w=640,h=480):
    x=.25 if inside else .75
    return {'track_id':12,'class_name':'person','time_since_update':0,'confidence':.9,
            'cx':0,'cy':0,'bbox':[(x-.05)*w,.3*h,(x+.05)*w,.75*h]}

def test_entry_stay_exit_reenter_new_episode_without_grace_suppression(monkeypatch):
    obj=checker(monkeypatch);router=ConfirmedAlertTransitions();cache=BehaviorOverlayCache('session')
    episodes=[];alerts=[]
    for stamp,inside in enumerate([False,True,True,False,True,True]):
        tracks=[person(inside)];direct=obj.analyze(tracks,640,480)
        assert len(direct)==(1 if stamp in (1,4) else 0)
        cache.update('behavior',{'stream_session':'session','observed_at':stamp,'frame_number':stamp,'overlay_events':obj.overlay_events},now=stamp)
        enriched,banners=cache.attach(tracks,now=stamp)
        assert bool(enriched[0]['behaviors'])==inside and not banners
        delivery=router.update(cache.confirmed_events(tracks,now=stamp),tracks,now=stamp)
        assert len(delivery)==(1 if stamp in (1,4) else 0)
        alerts+=delivery
        if delivery:episodes.append(delivery[0]['metadata']['episode_id'])
    assert len(set(episodes))==2 and all(a['severity']=='high' for a in alerts)

@pytest.mark.parametrize('w,h',[(640,480),(1920,1080),(1280,720)])
def test_foot_point_scales_with_actual_source_not_display(monkeypatch,w,h):
    obj=checker(monkeypatch);alerts=obj.analyze([person(w=w,h=h)],w,h)
    assert len(alerts)==1
    assert alerts[0]['metadata']['position']==pytest.approx((.25*w,.75*h))

def test_wrong_camera_polygon_and_stale_person_ignored(monkeypatch):
    obj=checker(monkeypatch,polygon_camera='classroom')
    assert obj.analyze([person()],640,480)==[] and obj.overlay_events==[]
    obj=checker(monkeypatch)
    assert obj.analyze([{**person(),'time_since_update':1}],640,480)==[]

def test_first_entry_ignores_old_cooldown_but_duplicate_episode_does_not_persist(monkeypatch):
    import redis,sqlalchemy,sqlalchemy.orm
    from app.services.tasks.alert_tasks import create_and_dispatch_alert,send_email_alert
    from app.services import safety_index
    obj=checker(monkeypatch);router=ConfirmedAlertTransitions();db=Mock();stored=[]
    context=Mock();context.__enter__=Mock(return_value=db);context.__exit__=Mock(return_value=False)
    def add(alert):alert.id=uuid.uuid4();alert.status='active';alert.created_at=datetime.now(timezone.utc);stored.append(alert)
    db.add.side_effect=add
    monkeypatch.setattr(sqlalchemy,'create_engine',Mock());monkeypatch.setattr(sqlalchemy.orm,'Session',Mock(return_value=context))
    keys=set();r=Mock()
    def reserve(key,*args,**kwargs):
        if key.startswith('alert_cooldown:') or key in keys:return False
        keys.add(key);return True
    r.set.side_effect=reserve
    monkeypatch.setattr(redis.Redis,'from_url',Mock(return_value=r))
    monkeypatch.setattr(safety_index,'publish_safety_index_sync',Mock());monkeypatch.setattr(send_email_alert,'delay',Mock())
    for stamp in (0,2):
        obj.analyze([person()],640,480)
        alert=router.update(obj.overlay_events,[person()],now=stamp)[0]
        create_and_dispatch_alert.run(str(uuid.UUID(int=1)),alert)
        create_and_dispatch_alert.run(str(uuid.UUID(int=1)),alert)
        obj.analyze([person(False)],640,480)
    assert len(stored)==2 and r.publish.call_count==2 and len(keys)==2
    for call in r.publish.call_args_list:
        assert json.loads(call.args[1])['alert']['alert_type']=='restricted_zone'

def test_distinct_zone_episodes_survive_cache_and_router(monkeypatch):
    obj=checker(monkeypatch);obj._zones.append({**obj._zones[0],'id':'second-zone'})
    obj.analyze([person()],640,480)
    cache=BehaviorOverlayCache('session');cache.update('behavior',{'stream_session':'session','observed_at':1,'overlay_events':obj.overlay_events},now=1)
    assert len(cache.confirmed_events([person()],now=1))==2
    assert len(ConfirmedAlertTransitions().update(cache.confirmed_events([person()],now=1),[person()],now=1))==2


@pytest.mark.parametrize('y,expected',[(.75,True),(.94,True),(.951,False)])
def test_vertical_tolerance_without_changing_polygon(y,expected):
    before=[dict(p) for p in POINTS]
    assert ZoneChecker.hit_test(.25,y,POINTS,.05)==expected
    assert POINTS==before
    assert not ZoneChecker.hit_test(.45,y,POINTS,.05)


def test_lower_body_reference_and_same_episode(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,'RESTRICTED_ZONE_REFERENCE_POINT','LOWER_BODY_POINT')
    monkeypatch.setattr(settings,'RESTRICTED_ZONE_FOOT_TOLERANCE',0)
    obj=checker(monkeypatch);t=person();t['bbox']=[128,240,192,465.6]
    assert ZoneChecker.reference_point(t['bbox'],640,480,'FOOT_POINT')[1]==pytest.approx(.97)
    assert ZoneChecker.reference_point(t['bbox'],640,480,'LOWER_BODY_POINT')[1]==pytest.approx(.923)
    obj._zones[0]['points']=[{'x':.1,'y':.6},{'x':.4,'y':.6},{'x':.4,'y':.94},{'x':.1,'y':.94}]
    assert len(obj.analyze([t],640,480))==1
    episode=obj.overlay_events[0]['episode_id']
    assert obj.analyze([t],640,480)==[] and obj.overlay_events[0]['episode_id']==episode
