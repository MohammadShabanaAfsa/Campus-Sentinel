"""Behavior inputs, episode transitions and production-overlay regressions."""
from unittest.mock import Mock
import pytest
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions
from ai_engine.vision.behavior_overlay import event
from ai_engine.behavioral.movement import MovementAnalyzer

def track(x=100,stale=0):return {'track_id':1,'class_name':'person','bbox':[x,100,x+100,300],'cx':x+50,'cy':200,'time_since_update':stale}

def test_alerts_transition_once_reconfirm_and_keep_camera_events_separate():
    router=ConfirmedAlertTransitions();person=track();person['identity']={'track_id':1,'verified':True,'method':'qr','roll_no':'S1','name':'Example'}
    events=[event('phone_use','low',1),event('eating','low',1),event('talking','low',1),event('crowd_density','medium',person_count=24)]
    alerts=router.update(events,[person],now=100)
    assert len(alerts)==4 and 'S1 Example' in alerts[0]['title']
    assert alerts[-1]['metadata']['track_id'] is None
    for _ in range(10):assert router.update(events,[person],now=101)==[]
    assert router.update([],[person],now=102)==[]
    assert router.update(events,[person],now=103)==[]  # Brief loss cannot duplicate an episode.
    assert router.update([],[person],now=107)==[]
    assert len(router.update(events,[person],now=108))==4

@pytest.mark.parametrize('positions',[[100,102,98,101,99,100]*4,list(range(100,340,10)),[100]*8+[300]+[100]*8])
def test_jitter_normal_motion_and_single_jump_are_not_running(positions,monkeypatch):
    import ai_engine.behavioral.movement as module
    clock=[100.0];monkeypatch.setattr(module.time,'time',lambda:clock[0]);analyzer=MovementAnalyzer('fixture')
    for x in positions:
        clock[0]+=.5
        assert analyzer.analyze([track(x)])==[]
        assert analyzer.overlay_events==[]

def test_near_zero_baseline_cannot_confirm_acceleration(monkeypatch):
    import ai_engine.behavioral.movement as module
    clock=[100.0];monkeypatch.setattr(module.time,'time',lambda:clock[0]);analyzer=MovementAnalyzer('fixture')
    x=100
    for speed in [0]*15+[200]*5:
        x+=speed*.5;clock[0]+=.5
        alerts=analyzer.analyze([track(x)])
        assert not any(a['metadata']['movement_type']=='sudden_acceleration' for a in alerts)

def test_atomic_alert_cooldown_prevents_db_and_publish(monkeypatch):
    import redis,sqlalchemy.orm,sqlalchemy
    from app.services.tasks.alert_tasks import create_and_dispatch_alert
    r=Mock();r.set.return_value=False
    monkeypatch.setattr(redis.Redis,'from_url',Mock(return_value=r))
    monkeypatch.setattr(sqlalchemy,'create_engine',Mock())
    session=Mock();monkeypatch.setattr(sqlalchemy.orm,'Session',session)
    create_and_dispatch_alert.run('fixture',{'alert_type':'phone_use','severity':'low','metadata':{'track_id':1}})
    assert r.set.call_args.kwargs['nx'] is True
    session.assert_not_called();r.publish.assert_not_called()

def test_tracker_does_not_assign_cross_class_detection():
    import numpy as np
    from ai_engine.tracking.tracker import ByteTracker
    tracker=ByteTracker('fixture',min_hits=1)
    person={**track(),'confidence':.9};car={**person,'class_name':'car'}
    first=tracker.update([person],np.zeros((400,600,3),np.uint8))[0]['track_id']
    output=tracker.update([car],np.zeros((400,600,3),np.uint8))
    assert next(t for t in output if t['class_name']=='car')['track_id']!=first

def test_qr_survives_visible_lifetime_but_expires_after_missing_grace():
    import numpy as np
    from ai_engine.identity.qr_identity import QRIdentityTracker
    qr=QRIdentityTracker({'S1':'Example'},scan_interval=10000)
    qr._identities[1]={'track_id':1,'roll_no':'S1','name':'Example','verified':True,'method':'qr','expires_at':1}
    qr._last_scan=100
    frame=np.zeros((400,600,3),np.uint8)
    assert qr.update(frame,[track()],now=100)[0]['identity']
    assert qr.update(frame,[track()],now=200)[0]['identity']
    qr.update(frame,[],now=201)
    assert qr.update(frame,[track()],now=202)[0]['identity']
    qr.update(frame,[],now=203);qr.update(frame,[],now=206)
    assert qr.update(frame,[track()],now=207)[0]['identity'] is None

def test_crowd_excludes_stale_people_and_detects_growth_from_zero(monkeypatch):
    import ai_engine.behavioral.crowd as module
    clock=[100.0];monkeypatch.setattr(module.time,'time',lambda:clock[0]);crowd=module.CrowdAnalyzer('fixture',density_threshold=3)
    for stamp in range(100,106):
        clock[0]=stamp;crowd.analyze([track(stale=2)])
    people=[{**track(i*150),'track_id':i} for i in range(6)]
    for stamp in range(106,110):clock[0]=stamp;crowd.analyze(people)
    assert {e['type'] for e in crowd.overlay_events}>={'crowd_surge','crowd_density'}
    assert all(e['track_id'] is None for e in crowd.overlay_events)

def test_zone_drawer_pixel_coordinates_are_normalized():
    from ai_engine.behavioral.zone_checker import ZoneChecker
    points=ZoneChecker._normalize_points([{'x':320,'y':180}])
    assert points==[{'x':.5,'y':.5}]

def test_talking_missing_sample_preserves_window_without_counting_time(monkeypatch):
    import ai_engine.classroom.student_state as rules
    clock=[100.0];monkeypatch.setattr(rules.time,'time',lambda:clock[0]);talk=rules.TalkingDetector('fixture')
    for i in range(16):clock[0]=100+i;talk.update(1,{'mar':.1 if i%2 else .3})
    old=talk._states[1].mar_history.copy();clock[0]=116
    assert not talk.update(1,{})['is_talking']
    assert talk._states[1].mar_history==old
    clock[0]=117;result=talk.update(1,{'mar':.1})
    assert result['duration_secs']==8  # Pause excludes the two unobserved seconds.

def test_visible_hand_model_recovers_wrist_without_pose():
    import numpy as np
    from types import SimpleNamespace
    from ai_engine.classroom.face_pose_analyzer import FacePoseAnalyzer
    analyzer=FacePoseAnalyzer.__new__(FacePoseAnalyzer);analyzer.camera_id='fixture';analyzer._face_mesh=None;analyzer._pose=None
    analyzer._hands=Mock(process=Mock(return_value=SimpleNamespace(multi_hand_landmarks=[SimpleNamespace(landmark=[SimpleNamespace(x=.5,y=.6)])],
        multi_handedness=[SimpleNamespace(classification=[SimpleNamespace(label='Left',score=.9)])])))
    result=analyzer.analyze_crop(np.zeros((400,200,3),np.uint8))
    assert result['wrists']['right']==(.5,.6) and result['wrist_sources']['right']=='hands'
