from collections import deque
from unittest.mock import Mock
import math
import numpy as np

from ai_engine.behavioral.movement import MovementAnalyzer, MovementState
from ai_engine.vision.behavior_overlay import BehaviorOverlayCache, event, PERSON_LABELS
from ai_engine.vision.frame_annotator import FrameAnnotator


def test_internal_zigzag_never_emits_alert_or_overlay(monkeypatch):
    import ai_engine.behavioral.movement as module
    monkeypatch.setattr(module.time,'time',lambda:101)
    analyzer=MovementAnalyzer('test')
    state=MovementState(12,last_pos=(100,100),last_time=100)
    state.directions=deque([0,math.pi]*6,maxlen=20)
    analyzer._states[12]=state
    assert analyzer.analyze([dict(track_id=12,class_name='person',cx=101,cy=100)])==[]
    assert analyzer.overlay_events==[] and not state.alerted


def test_stale_zigzag_filtered_and_area_renamed(monkeypatch):
    import cv2
    cache=BehaviorOverlayCache('session')
    cache.update('behavior',dict(stream_session='session',observed_at=100,frame_number=30,
        overlay_events=[event('zigzag_movement','high',12),event('restricted_zone','high',12)]),now=100)
    track=dict(track_id=12,class_name='person',bbox=[20,100,150,250],confidence=.87)
    tracks,_=cache.attach([track],now=100)
    texts=[]
    monkeypatch.setattr(cv2,'putText',lambda image,text,*args,**kwargs:texts.append(text))
    FrameAnnotator().draw(np.zeros((300,400,3),np.uint8),tracks)
    assert 'RESTRICTED AREA PROHIBITED' in texts
    assert not any('ZIGZAG' in text or 'RESTRICTED ZONE' in text for text in texts)
    assert 'zigzag_movement' not in PERSON_LABELS


def test_queued_zigzag_alert_is_discarded_before_database_access():
    from app.services.tasks.alert_tasks import create_and_dispatch_alert
    assert create_and_dispatch_alert.run('not-a-camera',dict(alert_type='abnormal_movement',metadata={'movement_type':'zigzag_movement'})) is None


def test_existing_alert_and_area_names_use_display_wording():
    from app.schemas.alert import AlertResponse
    from app.schemas.camera import RestrictedZoneResponse
    assert AlertResponse.display_area_wording('Restricted Zone Violation')=='Restricted Area Violation'
    assert AlertResponse.display_area_wording(None) is None
    assert RestrictedZoneResponse.display_area_wording('RESTRICTED ZONE')=='RESTRICTED AREA'
