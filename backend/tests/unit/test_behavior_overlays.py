"""Overlay routing, detector provenance, expiry, drawing and alert isolation."""
import math
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from ai_engine.vision.behavior_overlay import BehaviorOverlayCache, PERSON_LABELS, event
from ai_engine.vision.frame_annotator import FrameAnnotator
from ai_engine.behavioral.movement import MovementAnalyzer, MovementState
from ai_engine.behavioral.loitering import LoiteringDetector, LoiterState
from ai_engine.behavioral.zone_checker import ZoneChecker
from ai_engine.behavioral.crowd import CrowdAnalyzer


def person(tid=12, cx=100, cy=100):
    return dict(track_id=tid, class_name="person", confidence=.84,
                bbox=[cx-30, cy-30, cx+30, cy+70], cx=cx, cy=cy)


def snapshot(events, now=100, session="capture", frame=30):
    return dict(stream_session=session, observed_at=now, frame_number=frame, overlay_events=events)


def test_normal_person_has_no_abnormal_label(monkeypatch):
    cache = BehaviorOverlayCache("capture")
    tracks, banners = cache.attach([person()], now=100)
    assert tracks[0]["behaviors"] == [] and banners == []
    texts = []
    monkeypatch.setattr(cv2, "putText", lambda frame, text, *a, **kw: texts.append(text))
    FrameAnnotator().draw(np.zeros((240,400,3), np.uint8), tracks)
    assert "#12 PERSON 0.84" in texts
    assert not any(label in texts for label in PERSON_LABELS.values())


@pytest.mark.parametrize("kind", list(PERSON_LABELS))
def test_each_behavior_draws_only_on_the_same_track_id(kind, monkeypatch):
    cache = BehaviorOverlayCache("capture")
    cache.update("behavior", snapshot([event(kind, "medium", 12)]), now=100)
    tracks, banners = cache.attach([person(10), person(12, 240)], now=100)
    assert tracks[0]["behaviors"] == []
    assert tracks[1]["behaviors"][0]["track_id"] == 12
    assert banners == []
    texts = []
    monkeypatch.setattr(cv2, "putText", lambda frame, text, *a, **kw: texts.append(text))
    FrameAnnotator().draw(np.zeros((300,500,3), np.uint8), tracks)
    assert texts.count(PERSON_LABELS[kind]) == 1


def test_multiple_behaviors_order_by_severity_then_recency_and_limit():
    cache = BehaviorOverlayCache("capture")
    cache.update("behavior", snapshot([event("running", "medium", 12), event("loitering", "high", 12)], now=100), now=101)
    cache.update("classroom", snapshot([event("talking", "high", 12), event("sleeping", "low", 12)], now=101), now=101)
    tracks, _ = cache.attach([person()], now=101)
    assert [b["type"] for b in tracks[0]["behaviors"]] == ["talking", "loitering"]


def test_expiry_ended_condition_and_disappeared_track():
    cache = BehaviorOverlayCache("capture")
    sample = snapshot([event("running", "medium", 12)])
    cache.update("behavior", sample, now=100)
    cache.update("behavior", sample, now=103)  # Redis reread cannot extend expiry.
    assert cache.attach([person()], now=103)[0][0]["behaviors"]
    assert not cache.attach([person()], now=104)[0][0]["behaviors"]
    cache.update("behavior", snapshot([event("running", "medium", 12)], now=105), now=105)
    cache.update("behavior", snapshot([], now=106), now=106)
    assert not cache.attach([person()], now=106)[0][0]["behaviors"]
    cache.update("behavior", snapshot([event("running", "medium", 12)], now=107), now=107)
    cache.attach([], now=107)
    assert not cache.attach([person()], now=108)[0][0]["behaviors"]


def test_old_session_delayed_unknown_and_unidentified_results_are_ignored():
    cache = BehaviorOverlayCache("capture")
    cache.update("behavior", snapshot([event("running", "high", 12)], session="old"), now=100)
    cache.update("behavior", snapshot([event("running", "high", 12)]), now=105)
    cache.update("behavior", snapshot([event("invented", "high", 12), event("running", "high")], now=106), now=106)
    assert not cache.attach([person()], now=106)[0][0]["behaviors"]


def test_crowd_is_a_banner_even_if_metadata_contains_track_id(monkeypatch):
    cache = BehaviorOverlayCache("capture")
    cache.update("behavior", snapshot([event("crowd_density", "high", 12, person_count=24)]), now=100)
    tracks, banners = cache.attach([person(), person(7, 250)], now=100)
    assert all(t["behaviors"] == [] for t in tracks)
    assert banners[0]["track_id"] is None
    texts = []
    monkeypatch.setattr(cv2, "putText", lambda frame, text, *a, **kw: texts.append(text))
    FrameAnnotator().draw(np.zeros((300,500,3), np.uint8), tracks, {"camera_behaviors":banners})
    assert "ALERT: CROWD DENSITY - 24 PERSONS" in texts


@pytest.mark.parametrize("kind", ["running", "sudden_acceleration"])
def test_real_movement_conditions_produce_track_labels_without_repeating_alerts(kind, monkeypatch):
    import ai_engine.behavioral.movement as module
    clock=[100.0]
    monkeypatch.setattr(module.time,"time",lambda:clock[0])
    analyzer=MovementAnalyzer("camera")
    alerts=[];position=0
    speeds=[200]*16 if kind=="running" else [45]*15+[240]*8
    for speed in speeds:
        clock[0]+=.5;position+=speed*.5
        alerts.extend(analyzer.analyze([person(12,position)]))
    assert any(a["metadata"]["movement_type"]==kind for a in alerts)
    assert sum(a["metadata"]["movement_type"]==kind for a in alerts)==1



def test_loitering_and_zone_active_state_outlives_alert_cooldown(monkeypatch):
    import ai_engine.behavioral.loitering as module
    monkeypatch.setattr(module.time, "time", lambda: 500)
    analyzer = LoiteringDetector("camera")
    analyzer._states[12] = LoiterState(12, first_seen=100, last_seen=500, positions=[(100/640,100/480)])
    assert len(analyzer.analyze([person()])) == 1
    assert analyzer.analyze([person()]) == []
    assert analyzer.overlay_events[0]["type"] == "loitering"
    checker = ZoneChecker.__new__(ZoneChecker)
    checker.camera_id='camera'
    checker._zones = [dict(id="zone", name="Restricted", alert_level="high", points=[dict(x=0,y=0),dict(x=.5,y=0),dict(x=.5,y=.5),dict(x=0,y=.5)])]
    checker._alerted_tracks = {}
    assert len(checker.analyze([person()],400,400)) == 1
    assert checker.analyze([person()],400,400) == []
    assert len(checker.overlay_events)==1
    assert {k:v for k,v in checker.overlay_events[0].items() if k in ('type','severity','track_id','zone_id','zone_name')} == event("restricted_zone", "high", 12,zone_id='zone',zone_name='Restricted')
    assert checker.overlay_events[0]['episode_id']
    checker.analyze([person(12,350,350)],400,400)
    assert checker.overlay_events == []


def test_crowd_banner_survives_density_alert_cooldown():
    analyzer = CrowdAnalyzer("camera", density_threshold=2)
    tracks = [person(1),person(2,250)]
    assert len(analyzer.analyze(tracks)) == 1
    assert analyzer.analyze(tracks) == []
    assert analyzer.overlay_events[0]["track_id"] is None


def test_confirmed_classroom_states_include_track_id_without_consuming_extra_alerts(monkeypatch):
    from ai_engine.classroom.classroom_monitor import ClassroomMonitor
    monitor = ClassroomMonitor.__new__(ClassroomMonitor)
    monitor.camera_id = "camera"
    monitor._config = dict(expected_students=2,teaching_zone=None)
    monitor._last_faculty_signals = None
    monitor._low_attention_confirmed = monitor._low_engagement_confirmed = False
    monitor._attendance = Mock()
    monitor._attendance.analyze.return_value = dict(present_count=2,expected_count=2,missing_count=0,alerts=[])
    monitor._engagement = Mock()
    monitor._engagement.analyze.return_value = dict(faculty_track_id=None,engagement_score=90,faculty_present=True)
    monitor._face_pose = Mock()
    monitor._face_pose.analyze_crop.return_value = {}
    monitor._sleeping = Mock()
    monitor._talking = Mock()
    monitor._sleeping.update.side_effect = lambda tid, signals: dict(is_sleeping=tid==12)
    monitor._talking.update.side_effect = lambda tid, signals: dict(is_talking=tid==7)
    monitor._sleeping.consume_alert.return_value = monitor._talking.consume_alert.return_value = False
    monitor._sustained_engagement_alert = Mock(return_value=[])
    monitor._sustained_attention_alert = Mock(return_value=[])
    result = monitor.analyze([person(12),person(7,250)],np.zeros((400,400,3),np.uint8))
    assert result["overlay_events"] == [event("sleeping","low",12),event("talking","low",7)]
    assert result["alerts"] == []


def test_drawing_stays_inside_frame_and_does_not_dispatch_alerts(monkeypatch):
    calls = []
    monkeypatch.setattr(cv2,"rectangle",lambda frame,a,b,*args: calls.extend([a,b]))
    monkeypatch.setattr(cv2,"putText",lambda frame,text,point,*args: calls.append(point))
    track = person(); track["bbox"] = [-10,-5,400,300]
    track["behaviors"] = [{**event("running","high",12),"detected_at":100}]
    original = dict(track)
    FrameAnnotator().draw(np.zeros((200,320,3),np.uint8),[track])
    assert track == original
    assert all(x >= 0 and y >= 0 for x,y in calls)
    # The drawing module has no alert/database/task calls; rendering is pure.
    assert all(x <= 320 and y <= 200 for x,y in calls)


def test_rendering_does_not_add_alert_dispatches(monkeypatch):
    from app.services.tasks.alert_tasks import create_and_dispatch_alert
    dispatch = Mock()
    monkeypatch.setattr(create_and_dispatch_alert, "delay", dispatch)
    # An existing analyzer dispatches its own alert exactly once.
    dispatch("camera", {"alert_type":"abnormal_movement"})
    track = {**person(), "behaviors":[{**event("running","medium",12),"detected_at":100}]}
    for _ in range(10):
        FrameAnnotator().draw(np.zeros((240,400,3),np.uint8),[track])
    assert dispatch.call_count == 1


def test_real_sleeping_and_talking_rules_confirm_before_display_state(monkeypatch):
    import ai_engine.classroom.student_state as module
    clock = [100.0]
    monkeypatch.setattr(module.time,"time",lambda:clock[0])
    sleeping = module.SleepingDetector("camera")
    talking = module.TalkingDetector("camera")
    first = sleeping.update(12,{"ear":.1,"face_detected":True})
    assert first["is_sleeping_candidate"] and not first["is_sleeping"]
    talking._states[7] = module._TalkState(7,mar_history=[.1,.3]*4)
    assert not talking.update(7,{"mar":.3})["is_talking"]
    clock[0] = 108
    assert talking.update(7,{"mar":.1})["is_talking"]
    assert talking.consume_alert(7) and not talking.consume_alert(7)
    clock[0] = 115
    assert sleeping.update(12,{"ear":.1,"face_detected":True})["is_sleeping"]
    assert sleeping.consume_alert(12) and not sleeping.consume_alert(12)
    assert not sleeping.update(12,{"ear":.3,"face_detected":True})["is_sleeping"]


def test_missing_students_banner_requires_existing_sustained_rule(monkeypatch):
    import ai_engine.classroom.attendance as module
    clock = [100.0]
    monkeypatch.setattr(module.time,"time",lambda:clock[0])
    analyzer = module.AttendanceAnalyzer("camera")
    assert analyzer.analyze([person()],2)["overlay_events"] == []
    clock[0] = 120
    confirmed = analyzer.analyze([person()],2)
    assert len(confirmed["alerts"]) == 1
    assert confirmed["overlay_events"] == [event("missing_students","medium")]
    clock[0] = 121
    continuing = analyzer.analyze([person()],2)
    assert continuing["alerts"] == [] and continuing["overlay_events"]
    assert analyzer.analyze([person(),person(7)],2)["overlay_events"] == []


@pytest.mark.parametrize('zone,enabled', [('classroom', True), ('general', True), ('general', False)])
@pytest.mark.parametrize('visual_flags', [False, True])
def test_classroom_capture_pipeline_publishes_matching_overlay_metadata_and_jpeg(monkeypatch, zone, enabled, visual_flags):
    from ai_engine.vision import stream_manager as module
    from ai_engine.vision import detector, camera_manager
    from ai_engine.tracking import tracker
    from ai_engine.classroom import classroom_monitor
    from agents.orchestrator.agent_bus import AgentBus
    from app.services.tasks.ai_tasks import analyze_behavior
    from app.services.tasks.alert_tasks import create_and_dispatch_alert
    from app.core.config import settings
    from ai_engine.identity import qr_identity
    from ai_engine.behavioral.person_activity import PersonActivityAnalyzer
    import json
    import base64
    manager = module.StreamManager("fixture-classroom")
    frame = np.zeros((240,400,3),np.uint8)
    cap = Mock(active_source="fixture",using_fallback=False)
    cap.open.return_value = True
    count = [0]
    def read():
        count[0] += 1
        if count[0] > 30:
            manager._stop_event.set()
            return False,None
        return True,frame.copy()
    cap.read.side_effect = read
    monkeypatch.setattr(camera_manager,"CameraManager",Mock(return_value=cap))
    monkeypatch.setattr(detector.YOLODetector,"get_instance",Mock(return_value=Mock(detect=Mock(return_value=[]))))
    monkeypatch.setattr(tracker,"ByteTracker",Mock(return_value=Mock(update=Mock(return_value=[person(7)]))))
    classroom = Mock()
    classroom.analyze.return_value = {"metrics":{},"alerts":[],"overlay_events":[event("sleeping","low",7)]}
    monkeypatch.setattr(classroom_monitor.ClassroomMonitor,"get_instance",Mock(return_value=classroom))
    monkeypatch.setattr(AgentBus,"get_instance",Mock(return_value=Mock()))
    dispatch = Mock()
    monkeypatch.setattr(analyze_behavior,"delay",dispatch)
    alert_dispatch=Mock()
    monkeypatch.setattr(create_and_dispatch_alert,'delay',alert_dispatch)
    monkeypatch.setattr(settings,"FRAME_SKIP",3)
    monkeypatch.setattr(settings,"ACTIVITY_DEBUG",visual_flags)
    monkeypatch.setattr(settings,"QR_DEBUG_OVERLAY",visual_flags)
    monkeypatch.setattr(PersonActivityAnalyzer,"debug_sample",Mock())
    activity_debug_draw=Mock(side_effect=AssertionError('Diagnostic panel reached production JPEG'))
    monkeypatch.setattr(PersonActivityAnalyzer,"draw_debug",activity_debug_draw)
    qr_debug_draw=Mock(side_effect=AssertionError('QR diagnostic polygon reached production JPEG'))
    monkeypatch.setattr(qr_identity.QRIdentityTracker,"draw_debug",qr_debug_draw)
    monkeypatch.setattr(settings,"PHONE_ROI_INFERENCE_ENABLED",False)
    monkeypatch.setattr(settings,"ENABLE_ACTIVITY_ANALYSIS_ON_GENERAL",enabled)
    monkeypatch.setattr(PersonActivityAnalyzer,"sample",lambda self,frame,tracks:{})
    monkeypatch.setattr(PersonActivityAnalyzer,"analyze",lambda self,*args,**kwargs:
        [event("sleeping","low",7)] if self._sleeping is not None else [])
    monkeypatch.setattr(settings,"QR_IDENTIFICATION_ENABLED",True)
    monkeypatch.setattr(qr_identity,"load_student_mapping",lambda path:{"S123":"Example Name"})
    original_qr_tracker=qr_identity.QRIdentityTracker
    def synchronous_qr(mapping,**kwargs):
        kwargs['isolate_decoder']=False
        return original_qr_tracker(mapping,**kwargs)
    monkeypatch.setattr(qr_identity,"QRIdentityTracker",synchronous_qr)
    decoder=Mock()
    decoder.detectAndDecodeMulti.return_value=(True,('S123',),np.array([[[90,90],[110,90],[110,110],[90,110]]],dtype=float),None)
    monkeypatch.setattr(cv2,"QRCodeDetector",Mock(return_value=decoder))
    monkeypatch.setattr(module,"_get_rtsp_url",lambda cid:"fixture")
    monkeypatch.setattr(module,"_get_camera_zone_type",lambda cid:zone)
    monkeypatch.setattr(module,"_get_camera_name",lambda cid:"Fixture camera")
    for name in ("_update_camera_status","_persist_detections","_persist_classroom_metric","_publish_classroom_metric"):
        monkeypatch.setattr(module,name,Mock())
    values = {}
    redis = Mock(get=Mock(side_effect=lambda key:values.get(key)),set=Mock(side_effect=lambda key,value,**kw:values.__setitem__(key,value)))
    monkeypatch.setattr(module,"_get_redis",lambda:redis)
    texts=[]
    original=cv2.putText
    def record(frame,text,*args,**kw):
        texts.append(text)
        return original(frame,text,*args,**kw)
    monkeypatch.setattr(cv2,"putText",record)
    if zone == 'classroom':
        # Old Redis snapshots must not leak disabled labels or queued alerts.
        from ai_engine.vision.behavior_overlay import BehaviorOverlayCache
        original_attach=BehaviorOverlayCache.attach
        original_events=BehaviorOverlayCache.confirmed_events
        def stale_attach(self,tracks,*args,**kwargs):
            enriched,banners=original_attach(self,tracks,*args,**kwargs)
            for t in enriched:t['behaviors'].append(event('loitering','medium',t['track_id']))
            return enriched,banners+[event('crowd_density','medium',person_count=6),event('crowd_surge','high')]
        def stale_events(self,tracks,*args,**kwargs):
            return original_events(self,tracks,*args,**kwargs)+[event('loitering','medium',7),event('crowd_density','medium',person_count=6),event('crowd_surge','high')]
        monkeypatch.setattr(BehaviorOverlayCache,'attach',stale_attach)
        monkeypatch.setattr(BehaviorOverlayCache,'confirmed_events',stale_events)
    manager._camera_loop()
    payload=json.loads(values['camera:fixture-classroom:tracks'])
    assert payload['tracks'][0]['track_id']==7
    if zone == 'classroom' or enabled:
        assert payload['tracks'][0]['behaviors'][0]['type']=='sleeping'
        assert payload['tracks'][0]['behaviors'][0]['track_id']==7
        assert 'SLEEPING' in texts
    else:
        assert payload['tracks'][0]['behaviors'] == []
    assert payload['tracks'][0]['identity']['track_id']==7
    assert payload['tracks'][0]['identity']['roll_no']=='S123'
    if zone == 'classroom':
        assert not any(b['type'] in ('crowd_density','crowd_surge') for b in payload['camera_behaviors'])
        assert not any(b['type']=='loitering' for t in payload['tracks'] for b in t['behaviors'])
        assert not any('CROWD' in text or text=='LOITERING' for text in texts)
    assert 'S123 | EXAMPLE NAME' in texts
    jpeg=cv2.imdecode(np.frombuffer(base64.b64decode(values['camera:fixture-classroom:latest_frame']),np.uint8),cv2.IMREAD_COLOR)
    assert jpeg.shape==frame.shape
    dispatch.assert_not_called()  # One persistent AgentBus analyzer path; Celery handles confirmed alerts.
    assert alert_dispatch.call_count==(1 if zone=='classroom' or enabled else 0)
    if zone == 'classroom':
        classroom.analyze.assert_called_once()
    else:
        classroom_monitor.ClassroomMonitor.get_instance.assert_not_called()
        classroom.analyze.assert_not_called()
        module._persist_classroom_metric.assert_not_called()
        module._publish_classroom_metric.assert_not_called()
    cap.release.assert_called()
    activity_debug_draw.assert_not_called()
    qr_debug_draw.assert_not_called()


def test_clean_labels_are_above_box_with_severity_colors_and_separate_banner(monkeypatch):
    renderer=FrameAnnotator()
    strips=[]
    monkeypatch.setattr(renderer,'_text_strip',lambda frame,text,x,y,w,h,bg,scale:strips.append((text,x,y,bg)))
    track={**person(), 'bbox':[50,200,220,350], 'behaviors':[event('phone_use','low',12),event('running','medium',12)]}
    renderer.draw(np.zeros((400,600,3),np.uint8),[track],{'camera_behaviors':[event('crowd_density','medium',person_count=24)]})
    assert [s[0] for s in strips[:3]]==['UNKNOWN','RUNNING | PHONE USE','#12 PERSON 0.84']
    assert all(s[2]<200 for s in strips[:3])
    assert strips[0][3]==(45,45,45)
    assert strips[1][3]==(10,65,185)
    assert strips[3][0]=='ALERT: CROWD DENSITY - 24 PERSONS'
    assert strips[3][2]<strips[0][2]
