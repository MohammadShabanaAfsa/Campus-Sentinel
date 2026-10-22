from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid
import pytest
from app.core.config import settings
from app.schemas.camera import CampusEventConfiguration
from ai_engine.behavioral.campus_events import CampusEvents
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions

POLYGON=[{'x':.2,'y':.2},{'x':.8,'y':.2},{'x':.8,'y':.9},{'x':.2,'y':.9}]

def track(tid=1,x=.5,y=.5,kind='person',stale=0):
    return {'track_id':tid,'class_name':kind,'bbox':[x*1000-50,y*1000-200,x*1000+50,y*1000+200],
            'time_since_update':stale,'confidence':.9}

@pytest.fixture
def analyzer(monkeypatch):
    monkeypatch.setattr(settings,'ACTIVITY_DEBUG',False)
    return CampusEvents(settings)

def sample(a,now,tracks,signals=None,wall_time=None):return a.analyze(tracks,signals or {},(1000,1000),now=now,wall_time=wall_time)
def only(events,kind):return [e for e in events if e['type']==kind]

def fighting_sample(a,index):
    flip=index%2;x=.43 if not flip else .46
    tracks=[track(2,x),track(5,1-x)]
    wrist=(.1,.1) if not flip else (.9,.9)
    signals={t['track_id']:{'fight_wrists':{'left':wrist,'right':wrist}} for t in tracks}
    return tracks,sample(a,index*.5,tracks,signals)

def test_fight_sustained_combined_evidence_confirms_once_and_separation_clears(analyzer):
    router=ConfirmedAlertTransitions();alerts=[]
    for index in range(15):
        tracks,events=fighting_sample(analyzer,index)
        alerts.extend(router.update(events,tracks,now=index*.5))
        if index<12:assert not only(events,'suspected_fight')
    assert len(alerts)==1 and alerts[0]['severity']=='high'
    assert alerts[0]['title']=='SUSPECTED FIGHT — TRACKS #2 / #5'
    assert analyzer.pairs[(2,5)]['phase']=='FIGHT_CONFIRMED'
    for now in (8,9,10):assert only(sample(analyzer,now,[track(2,.1),track(5,.9)]),'suspected_fight')
    assert not only(sample(analyzer,11,[track(2,.1),track(5,.9)]),'suspected_fight')

@pytest.mark.parametrize('mode',['conversation','hug','handshake','walking','brief'])
def test_fight_normal_interactions_do_not_confirm(analyzer,mode):
    for index in range(20):
        if mode=='brief' and index<4:
            _,events=fighting_sample(analyzer,index)
        else:
            x=.43+(.001*index if mode=='walking' else 0)
            tracks=[track(2,x),track(5,x+.10)]
            wrist=(.9,.9) if mode=='handshake' and index==1 else (.5,.5)
            signals={t['track_id']:{'fight_wrists':{'left':wrist}} for t in tracks}
            events=sample(analyzer,index*.5,tracks,signals)
        assert not only(events,'suspected_fight')

@pytest.mark.parametrize('kind',['backpack','handbag','suitcase'])
def test_abandoned_bag_owner_leaves_stationary_confirms_once(analyzer,kind):
    bag=track(9,.52,kind=kind);owner=track(1,.5)
    assert not only(sample(analyzer,0,[bag,owner]),'abandoned_bag')
    router=ConfirmedAlertTransitions();alerts=[]
    for now in range(1,51):
        events=sample(analyzer,now,[bag])
        if now<46:assert not only(events,'abandoned_bag')
        alerts.extend(router.update(events,[bag],now=now))
    assert len(alerts)==1 and alerts[0]['severity']=='high'
    assert alerts[0]['metadata']['bag_track_ids']==[9]
    assert not only(sample(analyzer,51,[bag,owner]),'abandoned_bag')

@pytest.mark.parametrize('mode',['nearby','moving','brief','unassociated'])
def test_bag_no_false_confirmation(analyzer,mode):
    bag=track(9,.52,kind='backpack')
    if mode!='unassociated':sample(analyzer,0,[bag,track()])
    for now in range(1,70):
        objects=[track(9,.2+(now%10)*.04,kind='backpack')] if mode=='moving' else [bag]
        if mode=='nearby' or (mode=='brief' and now%10==0):objects.append(track())
        assert not only(sample(analyzer,now,objects),'abandoned_bag')

def schedule(start='06:00',end='21:00'):
    return {'schedule':{'enabled':True,'start':start,'end':end,'timezone':'Asia/Kolkata','zones':[]},'exit_zones':[]}

def test_after_hours_timezone_allowed_outside_and_one_episode(analyzer):
    analyzer.configure(schedule());router=ConfirmedAlertTransitions();alerts=[]
    inside=datetime(2026,10,13,6,0,tzinfo=timezone.utc) # 11:30 India.
    outside=datetime(2026,10,13,17,0,tzinfo=timezone.utc) # 22:30 India.
    assert not sample(analyzer,0,[track()],wall_time=inside)
    for now in (1,2,3,4):alerts.extend(router.update(sample(analyzer,now,[track()],wall_time=outside),[track()],now=now))
    assert len(alerts)==1 and alerts[0]['alert_type']=='after_hours_presence'
    assert not sample(analyzer,5,[],wall_time=outside)

def test_schedule_overnight_and_zone_override(analyzer):
    analyzer.configure(schedule('21:00','06:00'))
    late=datetime(2026,10,13,17,0,tzinfo=timezone.utc)
    for now in range(4):assert not sample(analyzer,now,[track()],wall_time=late)
    config=schedule();config['schedule']['zones']=[{'enabled':True,'points':POLYGON,'start':'21:00','end':'06:00'}]
    analyzer.configure(config)
    for now in range(4,8):assert not sample(analyzer,now,[track()],wall_time=late)

def test_after_hours_disabled_or_stale_is_not_presence(analyzer):
    for now in range(4):assert not sample(analyzer,now,[track(stale=1)])

@pytest.mark.parametrize('kind',['person','backpack','car'])
def test_exit_blockage_temporal_confirm_clear_one_alert(analyzer,kind):
    analyzer.configure({'exit_zones':[{'id':'exit','name':'Exit','enabled':True,'points':POLYGON}]})
    assert not sample(analyzer,0,[track(x=.05,kind=kind)])
    router=ConfirmedAlertTransitions();alerts=[]
    for now in range(1,16):
        objects=[track(kind=kind)];events=sample(analyzer,now,objects)
        if now<11:assert not only(events,'emergency_exit_blocked')
        alerts.extend(router.update(events,objects,now=now))
    assert len(alerts)==1 and alerts[0]['severity']=='high'
    assert not sample(analyzer,16,[track(x=.05,kind=kind)])
    assert analyzer.exits=={}

def test_exit_brief_entry_stale_track_and_config_clear(analyzer):
    analyzer.configure({'exit_zones':[{'id':'exit','name':'Exit','points':POLYGON}]})
    assert not sample(analyzer,0,[track()])
    assert not sample(analyzer,1,[track(stale=1)])
    for now in range(2,7):assert not sample(analyzer,now,[track()])
    analyzer.configure({'exit_zones':[]})
    assert not sample(analyzer,7,[track()])

@pytest.mark.asyncio
async def test_config_api_preserves_other_features_and_validates():
    from app.api.v1.endpoints.cameras import save_campus_events
    camera=SimpleNamespace(config={'vehicle_counting_line':{'enabled':True},'classroom_enabled':True})
    db=SimpleNamespace(get=AsyncMock(return_value=camera),commit=AsyncMock())
    config=CampusEventConfiguration(**schedule())
    await save_campus_events(uuid.uuid4(),config,db,None)
    assert camera.config['vehicle_counting_line']=={'enabled':True} and camera.config['classroom_enabled']
    with pytest.raises(ValueError):CampusEventConfiguration(schedule={'start':'25:00'})
    with pytest.raises(ValueError):CampusEventConfiguration(schedule={'timezone':'invalid/timezone'})
    with pytest.raises(ValueError):CampusEventConfiguration(exit_zones=[{'name':'Exit','points':[{'x':5,'y':4}]*3}])


@pytest.mark.parametrize('kind',['suspected_fight','abandoned_bag','fall_detected','loitering','crowd_surge','after_hours_presence','emergency_exit_blocked'])
def test_existing_alert_task_persists_and_broadcasts_new_types_once(kind,monkeypatch):
    from unittest.mock import Mock
    import json,redis,sqlalchemy,sqlalchemy.orm
    from app.services.tasks.alert_tasks import create_and_dispatch_alert,send_email_alert
    from app.services import safety_index
    from ai_engine.vision.behavior_overlay import event
    db=Mock();context=Mock();context.__enter__=Mock(return_value=db);context.__exit__=Mock(return_value=False)
    stored=[]
    def add(alert):
        alert.id=uuid.uuid4();alert.created_at=datetime.now(timezone.utc);alert.status='active';stored.append(alert)
    db.add.side_effect=add
    monkeypatch.setattr(sqlalchemy,'create_engine',Mock())
    monkeypatch.setattr(sqlalchemy.orm,'Session',Mock(return_value=context))
    r=Mock();r.set.side_effect=[True,False]
    monkeypatch.setattr(redis.Redis,'from_url',Mock(return_value=r))
    monkeypatch.setattr(safety_index,'publish_safety_index_sync',Mock())
    monkeypatch.setattr(send_email_alert,'delay',Mock())
    severity='medium' if kind=='loitering' else 'high'
    tid=2 if kind in ('loitering','fall_detected') else None
    data=ConfirmedAlertTransitions().update([event(kind,severity,tid,track_ids=[2,5])],[],now=0)[0]
    cid=str(uuid.uuid4())
    create_and_dispatch_alert.run(cid,data)
    create_and_dispatch_alert.run(cid,data)
    assert len(stored)==1 and stored[0].severity==severity and stored[0].alert_type==kind
    assert stored[0].extra_data['track_ids']==[2,5]
    r.publish.assert_called_once()
    channel,payload=r.publish.call_args.args
    assert channel=='alerts_channel' and json.loads(payload)['alert']['alert_type']==kind


def test_new_events_are_only_camera_banners(monkeypatch):
    import numpy as np,cv2
    from ai_engine.vision.behavior_overlay import event
    from ai_engine.vision.frame_annotator import FrameAnnotator
    texts=[]
    monkeypatch.setattr(cv2,'putText',lambda frame,text,*args,**kw:texts.append(text))
    FrameAnnotator().draw(np.zeros((480,640,3),np.uint8),[track()],
        {'camera_behaviors':[event('suspected_fight','high',track_ids=[2,5]),event('abandoned_bag','high')]})
    assert 'UNKNOWN' in texts and any('SUSPECTED FIGHT - TRACKS #2 / #5' in t for t in texts)
    assert not any(t=='SUSPECTED FIGHT' or t=='ABANDONED BAG' for t in texts)
