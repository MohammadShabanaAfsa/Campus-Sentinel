"""Deterministic episode tests using real track IDs and capture timestamps."""
import numpy as np
import pytest
from ai_engine.behavioral.loitering import LoiteringDetector
from ai_engine.behavioral.crowd import CrowdAnalyzer
from ai_engine.vision.behavior_overlay import BehaviorOverlayCache,event
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions
from ai_engine.vision.frame_annotator import FrameAnnotator


def people(count,stale=0):
    return [dict(track_id=i,class_name='person',cx=40+i*30,cy=200,
                 bbox=[20+i*30,100,60+i*30,300],confidence=.9,time_since_update=stale) for i in range(count)]


def only(alerts,kind):return [a for a in alerts if a['alert_type']==kind]


def baseline(analyzer,count=6):
    for stamp in range(6):analyzer.analyze(people(count),now=stamp)


def test_loitering_duration_is_normalized_medium_and_edge_triggered():
    det=LoiteringDetector('general',threshold_secs=300)
    for stamp in range(300):assert det.analyze(people(1),640,480,now=stamp)==[]
    alert=det.analyze(people(1),640,480,now=300)
    assert len(alert)==1 and alert[0]['severity']=='medium'
    assert alert[0]['metadata']['position']==(40/640,200/480)
    assert det.overlay_events[0]['track_id']==0
    for stamp in range(301,601):assert det.analyze(people(1),640,480,now=stamp)==[]
    assert det.overlay_events[0]['severity']=='medium'


@pytest.mark.parametrize('missing',[[],people(1,stale=1)])
def test_loitering_disappearance_or_stale_track_uses_grace(missing):
    det=LoiteringDetector('general',threshold_secs=10)
    for stamp in range(10):det.analyze(people(1),now=stamp)
    det.analyze(missing,now=10)
    assert det._states and det.overlay_events==[]
    assert det.analyze(people(1),now=11)
    det.analyze(missing,now=12);det.analyze(missing,now=15)
    assert det._states=={}
    assert det.analyze(people(1),now=16)==[]


def test_loitering_significant_motion_restarts_episode():
    det=LoiteringDetector('general',threshold_secs=10)
    for stamp in range(10):det.analyze(people(1),now=stamp)
    assert det.analyze(people(1),now=10)
    moved=[{**people(1)[0],'cx':140}]
    assert det.analyze(moved,now=11)==[]
    assert det._states[0].first_seen==11
    for stamp in range(12,21):det.analyze(moved,now=stamp)
    assert det.analyze(moved,now=21)


def test_loitering_slow_drift_cannot_hide_behind_capped_history():
    det=LoiteringDetector('general',threshold_secs=300)
    for stamp in range(350):
        tracks=[{**people(1)[0],'cx':40+stamp*.1}]
        det.analyze(tracks,now=stamp)
    assert det._states[0].duration<300 and det.overlay_events==[]
    assert len(det._states[0].positions)<=200


def test_debug_short_duration_is_opt_in(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,'ACTIVITY_DEBUG',False)
    monkeypatch.setattr(settings,'LOITERING_DEBUG_THRESHOLD_SECS',2)
    assert LoiteringDetector('production').threshold_secs==300
    monkeypatch.setattr(settings,'ACTIVITY_DEBUG',True)
    assert LoiteringDetector('debug').threshold_secs==2


@pytest.mark.parametrize('camera',['general','classroom'])
@pytest.mark.parametrize('count,expected',[(4,False),(5,True),(6,True)])
def test_density_boundaries(camera,count,expected):
    det=CrowdAnalyzer(camera)
    alerts=only(det.analyze(people(count),now=0),'crowd_density')
    assert bool(alerts)==expected
    if alerts:assert alerts[0]['metadata']['track_id'] is None


@pytest.mark.parametrize('camera',['general','classroom'])
def test_production_loitering_grace_and_single_alert(camera):
    det=LoiteringDetector(camera,threshold_secs=300,movement_threshold=.05)
    router=ConfirmedAlertTransitions()
    assert det.analyze(people(1),now=0)==[]
    for stamp in range(1,299):det.analyze(people(1),now=stamp)
    det.analyze([],now=299)
    assert len(det.analyze(people(1),now=300))==1
    alerts=router.update(det.overlay_events,people(1),now=300)
    assert len(alerts)==1 and alerts[0]['severity']=='medium'
    det.analyze(people(1),now=301)
    assert router.update(det.overlay_events,people(1),now=301)==[]
    moved=[{**people(1)[0],'cx':140}]
    assert det.analyze(moved,now=302)==[] and det.overlay_events==[]
    det.analyze([],now=303)
    assert det.analyze(moved,now=307)==[]
    assert det._states[0].first_seen==307


@pytest.mark.parametrize('camera',['general','classroom'])
def test_five_person_density_banner_and_alert_once(camera):
    det=CrowdAnalyzer(camera);router=ConfirmedAlertTransitions();cache=BehaviorOverlayCache('session')
    for stamp,count in [(0,4),(1,5),(2,6),(3,5)]:
        det.analyze(people(count)+people(3,stale=1),now=stamp)
        cache.update('behavior',{'stream_session':'session','observed_at':stamp,'frame_number':stamp,
                                 'overlay_events':det.overlay_events},now=stamp)
        tracks,banners=cache.attach(people(count),now=stamp)
        assert all(not t['behaviors'] for t in tracks)
        assert bool([b for b in banners if b['type']=='crowd_density'])==(count>=5)
        alerts=only(router.update(cache.confirmed_events(tracks,now=stamp),tracks,now=stamp),'crowd_density')
        assert len(alerts)==(1 if stamp==1 else 0)
        if alerts:assert alerts[0]['title']=='CROWD DENSITY — 5 PERSONS'


def test_density_stale_and_duplicate_tracks_do_not_inflate_count():
    det=CrowdAnalyzer('general',density_threshold=3)
    assert not only(det.analyze(people(2)+people(8,stale=1)+people(2),now=0),'crowd_density')


def test_density_one_alert_per_episode_with_flicker_debounce():
    det=CrowdAnalyzer('general',density_threshold=20)
    assert only(det.analyze(people(20),now=0),'crowd_density')
    for stamp in range(1,5):assert not only(det.analyze(people(24),now=stamp),'crowd_density')
    det.analyze(people(19),now=5)
    assert not only(det.analyze(people(20),now=6),'crowd_density')
    for stamp in range(7,11):det.analyze(people(19),now=stamp)
    assert only(det.analyze(people(20),now=11),'crowd_density')


def test_surge_requires_stable_baseline_and_sustained_growth_once():
    det=CrowdAnalyzer('general');baseline(det,6)
    for stamp in (6,7,8):assert not only(det.analyze(people(10),now=stamp),'crowd_surge')
    alert=only(det.analyze(people(10),now=9),'crowd_surge')
    assert len(alert)==1 and alert[0]['metadata']['growth_rate']==pytest.approx(2/3)
    for stamp in range(10,20):
        assert not only(det.analyze(people(10),now=stamp),'crowd_surge')
        assert any(e['type']=='crowd_surge' and e['track_id'] is None for e in det.overlay_events)


@pytest.mark.parametrize('count',[5,9])
def test_no_surge_at_fifty_percent_or_low_current_count(count):
    det=CrowdAnalyzer('general');baseline(det,6)
    for stamp in range(6,16):assert not only(det.analyze(people(count),now=stamp),'crowd_surge')


def test_spike_and_tracker_drop_do_not_create_surge():
    det=CrowdAnalyzer('general');baseline(det,10)
    assert not only(det.analyze(people(20),now=6),'crowd_surge')
    assert not only(det.analyze(people(10),now=7),'crowd_surge')
    assert not only(det.analyze([],now=8),'crowd_surge')
    for stamp in range(9,15):assert not only(det.analyze(people(10),now=stamp),'crowd_surge')


def test_reconnect_gap_discards_old_low_count_baseline():
    det=CrowdAnalyzer('general');baseline(det,6)
    for stamp in range(20,30):assert not only(det.analyze(people(20),now=stamp),'crowd_surge')


def test_repeated_timestamp_does_not_supply_confirmation_samples():
    det=CrowdAnalyzer('general');baseline(det,6)
    for _ in range(20):assert not only(det.analyze(people(10),now=6),'crowd_surge')
    assert det._surge_hits==1


def test_low_current_count_cannot_surge_even_with_large_growth():
    det=CrowdAnalyzer('general');baseline(det,2)
    for stamp in range(6,15):assert not only(det.analyze(people(5),now=stamp),'crowd_surge')


def test_surge_rearms_only_after_episode_clears():
    det=CrowdAnalyzer('general');baseline(det,6)
    for stamp in range(6,10):alerts=det.analyze(people(10),now=stamp)
    assert only(alerts,'crowd_surge')
    det.analyze(people(6),now=10)
    assert not only(det.analyze(people(10),now=11),'crowd_surge')
    for stamp in range(12,16):det.analyze(people(6),now=stamp)
    for stamp in range(16,20):alerts=det.analyze(people(10),now=stamp)
    assert only(alerts,'crowd_surge')


def test_timestamp_duration_not_number_of_calls_controls_surge():
    det=CrowdAnalyzer('general')
    for stamp in (0,2,5):det.analyze(people(6),now=stamp)
    for stamp in (6,6.1,6.2,6.3,6.4):assert not only(det.analyze(people(10),now=stamp),'crowd_surge')
    assert only(det.analyze(people(10),now=9),'crowd_surge')


def test_old_growth_baseline_expires_at_window_end():
    det=CrowdAnalyzer('general');baseline(det,6)
    for stamp in range(6,37):det.analyze(people(10),now=stamp)
    assert not det._surge_active
    assert not only(det.analyze(people(12),now=37),'crowd_surge')


def test_malformed_tracks_do_not_count_as_active_people():
    malformed=[{'class_name':'person'},dict(people(1)[0],confidence=float('nan'))]
    assert CrowdAnalyzer.active_people(malformed)==[]


def test_events_use_existing_router_once_and_render_at_correct_level(monkeypatch):
    person=people(1)[0];cache=BehaviorOverlayCache('fixture')
    snapshot={'stream_session':'fixture','observed_at':100,'overlay_events':[
        event('loitering','medium',0),event('crowd_density','medium',person_count=24),
        event('crowd_surge','high',person_count=24)]}
    cache.update('behavior',snapshot,now=100)
    tracks,banners=cache.attach([person],now=100)
    assert [e['type'] for e in tracks[0]['behaviors']]==['loitering']
    assert {e['type'] for e in banners}=={'crowd_density','crowd_surge'}
    router=ConfirmedAlertTransitions();events=cache.confirmed_events([person],now=100)
    alerts=router.update(events,tracks,now=100)
    assert len(alerts)==3 and router.update(events,tracks,now=101)==[]
    strips=[];renderer=FrameAnnotator()
    monkeypatch.setattr(renderer,'_text_strip',lambda frame,text,x,y,*args:strips.append((text,y)))
    renderer.draw(np.zeros((480,640,3),np.uint8),tracks,{'camera_behaviors':banners})
    assert any(text=='LOITERING' for text,y in strips)
    person_y=next(y for text,y in strips if text=='LOITERING')
    assert any('CROWD DENSITY - 24 PERSONS' in text and y<person_y for text,y in strips)
    assert any('CROWD SURGE - 24 PERSONS' in text and y<person_y for text,y in strips)
    assert not any('CROWD' in text for text,y in strips if text in ('LOITERING','UNKNOWN'))


@pytest.mark.parametrize('camera_id',['general-entrance','general-secondary'])
def test_agent_runs_both_rules_and_resets_crowd_on_new_session(camera_id,monkeypatch):
    from agents.behavior_agent.agent import BehaviorAgent
    agent=BehaviorAgent()
    monkeypatch.setattr(agent,'_run_movement',lambda *args:[])
    monkeypatch.setattr(agent,'_run_zones',lambda *args:[])
    monkeypatch.setattr(agent,'_run_abd',lambda *args:0)
    monkeypatch.setattr(agent,'_update_redis_state',lambda *args:None)
    monkeypatch.setattr(agent,'_persist_behavior_log',lambda *args:None)
    monkeypatch.setattr(agent.bus,'publish',lambda *args:None)
    message={'camera_id':camera_id,'tracks':people(1),'stream_session':'old','observed_at':0}
    agent._on_tracks(message);previous=agent._crowd_analyzers[camera_id]
    agent._on_tracks({**message,'stream_session':'new','observed_at':10})
    assert agent._crowd_analyzers[camera_id] is not previous
    assert camera_id in agent._loitering_detectors


def test_classroom_skips_crowd_loitering_but_executes_movement_and_zones(monkeypatch):
    from unittest.mock import Mock
    from agents.behavior_agent.agent import BehaviorAgent
    agent=BehaviorAgent();states=[]
    monkeypatch.setattr(agent,'_run_loitering',Mock(side_effect=AssertionError('Classroom loitering executed')))
    monkeypatch.setattr(agent,'_run_crowd',Mock(side_effect=AssertionError('Classroom crowd executed')))
    movement=Mock(return_value=[]);zones=Mock(return_value=[])
    monkeypatch.setattr(agent,'_run_movement',movement);monkeypatch.setattr(agent,'_run_zones',zones)
    monkeypatch.setattr(agent,'_run_abd',lambda *args:0)
    monkeypatch.setattr(agent,'_update_redis_state',lambda cid,state:states.append(state))
    monkeypatch.setattr(agent,'_persist_behavior_log',lambda *args:None)
    monkeypatch.setattr(agent.bus,'publish',lambda *args:None)
    agent._on_tracks({'camera_id':'classroom','zone_type':'classroom','tracks':people(6),
                      'stream_session':'session','observed_at':300})
    movement.assert_called_once();zones.assert_called_once()
    assert len(states)==1 and states[0]['person_count']==6 and states[0]['crowd_count']==0
    assert not agent._crowd_analyzers and not agent._loitering_detectors
    assert states[0]['overlay_events']==[]


def test_legacy_classroom_task_also_skips_disabled_analyzers(monkeypatch):
    from unittest.mock import Mock
    import json
    from app.services.tasks.ai_tasks import analyze_behavior
    from ai_engine.vision import stream_manager
    from ai_engine.behavioral.movement import MovementAnalyzer
    from ai_engine.behavioral.zone_checker import ZoneChecker
    monkeypatch.setattr(stream_manager,'_get_camera_zone_type',lambda cid:'classroom')
    monkeypatch.setattr(LoiteringDetector,'get_instance',Mock(side_effect=AssertionError('Unexpected loitering')))
    monkeypatch.setattr(CrowdAnalyzer,'get_instance',Mock(side_effect=AssertionError('Unexpected crowd')))
    movement=Mock(analyze=Mock(return_value=[]));zones=Mock(analyze=Mock(return_value=[]))
    monkeypatch.setattr(MovementAnalyzer,'get_instance',lambda cid:movement)
    monkeypatch.setattr(ZoneChecker,'get_instance',lambda cid:zones)
    analyze_behavior.run('classroom',json.dumps(people(6)),1)
    movement.analyze.assert_called_once();zones.analyze.assert_called_once()

def test_excessive_observation_gap_resets_even_without_empty_sample():
    det=LoiteringDetector('gap',threshold_secs=10)
    for stamp in range(9):det.analyze(people(1),now=stamp)
    assert det.analyze(people(1),now=12)==[]
    assert det._states[0].first_seen==12
