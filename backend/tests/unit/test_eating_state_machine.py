"""Eating-only production thresholds, hand phases, grace and alert regressions."""
import pytest
from app.core.config import settings
from ai_engine.behavioral.person_activity import PersonActivityAnalyzer
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions

PERSON={'track_id':12,'class_name':'person','bbox':[0,0,200,400],'time_since_update':0}


@pytest.fixture
def analyzer():
    config=settings.model_copy(update={'ACTIVITY_DEBUG':False,'EATING_DEBUG':False,'PHONE_EATING_DEBUG':False,
        'EATING_MOUTH_DISTANCE_THRESHOLD':.70,'EATING_AWAY_DISTANCE_THRESHOLD':.85,
        'EATING_MIN_EVENTS':3,'EATING_WINDOW_SECS':20})
    return PersonActivityAnalyzer('eating-fixture',config)


def observe(analyzer,now,left=1.1,right=None,quality=None,outside=False):
    wrists={side:(.5,.2+distance/4) for side,distance in [('left',left),('right',right)] if distance is not None}
    raw={'face_detected':True,'mouth_center':(.5,.2),'shoulders':{'left':(.25,.3),'right':(.75,.3)},
         'wrists':wrists,'landmark_visibility':{f'{side}_wrists':{'visibility':(quality or {}).get(side,.8),'in_crop':True} for side in wrists}}
    if outside:raw['landmark_visibility']['left_wrists']={'visibility':.2,'in_crop':False}
    return analyzer.analyze([PERSON],[],{12:raw},(400,600,3),now=now)


def test_one_cycle_includes_slow_leaving_without_extending_near_dwell(analyzer):
    for now,distance in [(0,1.1),(.5,.78),(1,.55),(2,.55),(2.25,.78),(3.5,.80),(4.5,1.1)]:
        assert observe(analyzer,now,distance)==[]
    state=analyzer.eating[12]
    assert len(state.events)==1 and state.hands['left']['phase']=='AWAY'


def test_all_observed_phases_and_hysteresis_preserve_one_cycle(analyzer):
    values=[(0,1.1,'AWAY'),(.5,.78,'APPROACHING'),(1,.55,'NEAR_MOUTH'),
            (1.5,.76,'LEAVING'),(1.75,.80,'LEAVING'),(2,.73,'LEAVING'),(2.5,1.1,'AWAY')]
    for stamp,distance,phase in values:
        observe(analyzer,stamp,distance)
        assert analyzer.eating[12].hands['left']['phase']==phase
    assert len(analyzer.eating[12].events)==1


def test_near_mouth_without_observed_return_is_not_complete(analyzer):
    observe(analyzer,0,1.1)
    for stamp in range(1,8):assert observe(analyzer,stamp,.55)==[]
    assert not analyzer.eating[12].events
    assert observe(analyzer,8,1.1)==[]  # A long chin rest is not a valid short contact.
    assert not analyzer.eating[12].events


def test_short_missing_wrist_pauses_progress_and_resumes(analyzer):
    observe(analyzer,0,1.1);observe(analyzer,1,.55)
    observe(analyzer,1.5,None)
    assert analyzer.eating[12].hands['left']['phase']=='NEAR_MOUTH'
    observe(analyzer,2,.55);observe(analyzer,2.5,.78);observe(analyzer,3,1.1)
    assert len(analyzer.eating[12].events)==1


def test_visible_leaving_can_resume_after_one_missing_sample(analyzer):
    observe(analyzer,0,1.1);observe(analyzer,1,.55);observe(analyzer,2,.78)
    observe(analyzer,2.25,None);observe(analyzer,2.75,1.1)
    assert len(analyzer.eating[12].events)==1


def test_one_missed_slower_sample_does_not_erase_cycle_progress(analyzer):
    observe(analyzer,0,1.1);observe(analyzer,1.7,.55)
    observe(analyzer,3.4,None)
    observe(analyzer,5.1,.55)
    assert analyzer.eating[12].hands['left']['near_since']==pytest.approx(5.1)
    observe(analyzer,6.1,.78);observe(analyzer,7.1,1.1)
    assert len(analyzer.eating[12].events)==1


def test_long_missing_gap_clears_incomplete_hand_phase(analyzer):
    observe(analyzer,0,1.1);observe(analyzer,1,.55)
    for stamp in (2,3,4,5):observe(analyzer,stamp,None)
    assert not analyzer.eating[12].hands
    assert observe(analyzer,6,1.1)==[] and not analyzer.eating[12].events


def test_leaving_frame_cannot_manufacture_a_cycle(analyzer):
    observe(analyzer,0,1.1);observe(analyzer,1,.55);observe(analyzer,2,.78)
    observe(analyzer,2.25,None,outside=True)
    assert not analyzer.eating[12].events
    observe(analyzer,2.75,1.1)
    assert not analyzer.eating[12].events


def test_moving_lower_visibility_hand_is_selected_and_tracks_independently(analyzer):
    quality={'left':.99,'right':.8}
    observe(analyzer,0,1.1,1.1,quality)
    observe(analyzer,.5,1.1,.78,quality)
    assert analyzer.eating[12].selected_wrist=='right'
    observe(analyzer,1,1.1,.55,quality)
    assert analyzer.eating[12].hands['left']['phase']=='AWAY'
    assert analyzer.eating[12].hands['right']['phase']=='NEAR_MOUTH'
    assert analyzer.eating[12].selected_wrist=='right'
    observe(analyzer,2,1.1,.78,quality);observe(analyzer,2.5,1.1,1.1,quality)
    assert len(analyzer.eating[12].events)==1


def test_three_cycles_confirm_low_once_through_existing_alert_router(analyzer):
    router=ConfirmedAlertTransitions();alerts=[]
    for start in (0,3,6):
        for stamp,distance in [(start,1.1),(start+1,.55),(start+2,1.1)]:
            events=observe(analyzer,stamp,distance)
            alerts.extend(router.update(events,[PERSON],now=stamp))
    for stamp in (9,10,11):alerts.extend(router.update(observe(analyzer,stamp,1.1),[PERSON],now=stamp))
    assert len(analyzer.eating[12].events)==3
    assert len(alerts)==1 and alerts[0]['alert_type']=='eating' and alerts[0]['severity']=='low'


def test_stationary_near_hand_cannot_hide_moving_other_hand(analyzer):
    quality={'left':.99,'right':.8}
    observe(analyzer,0,1.1,1.1,quality)
    observe(analyzer,.5,.55,1.1,quality)
    observe(analyzer,1,.55,.78,quality)
    assert analyzer.eating[12].selected_wrist=='right'
    observe(analyzer,1.5,.55,.55,quality)
    observe(analyzer,2,.55,.55,quality)
    assert analyzer.eating[12].selected_wrist=='right'


def test_completed_cycle_history_survives_one_missing_wrist_sample(analyzer):
    for start in (0,3):
        observe(analyzer,start,1.1);observe(analyzer,start+1,.55);observe(analyzer,start+2,1.1)
    observe(analyzer,6,None)
    assert len(analyzer.eating[12].events)==2
    observe(analyzer,7,1.1);observe(analyzer,8,.55)
    assert observe(analyzer,9,1.1)==[{'type':'eating','severity':'low','track_id':12}]


def test_old_cycles_expire_after_twenty_second_window(analyzer):
    for start in (0,3,6):
        observe(analyzer,start,1.1);observe(analyzer,start+1,.55);observe(analyzer,start+2,1.1)
    assert observe(analyzer,29,1.1)==[]
    assert not analyzer.eating[12].events


def test_one_cycle_debug_setting_never_replaces_production_three(analyzer):
    assert analyzer.settings.EATING_TEST_MIN_CYCLES==1
    observe(analyzer,0,1.1);observe(analyzer,1,.55)
    assert observe(analyzer,2,1.1)==[]
    assert len(analyzer.eating[12].events)==1 and analyzer.settings.EATING_MIN_EVENTS==3


def test_eating_only_log_has_required_values_without_other_detectors(analyzer,monkeypatch):
    import ai_engine.behavioral.person_activity as module
    import json
    analyzer.settings.EATING_DEBUG=True;records=[]
    monkeypatch.setattr(module.logger,'info',records.append)
    observe(analyzer,0,1.1)
    assert len(records)==1 and records[0].startswith('EATING_SAMPLE ')
    record=json.loads(records[0].split(' ',1)[1])
    assert set(record)=={'camera_id','track_id','selected_hand','wrist_visibility','left_wrist_visibility','right_wrist_visibility','normalized_distance','current_phase','completed_cycles'}


def test_eating_accepts_its_wrist_cutoff_without_changing_phone_inputs(analyzer):
    raw={'face_detected':True,'mouth_center':(.5,.2),'shoulders':{'left':(.25,.3),'right':(.75,.3)},'wrists':{},
         'eating_wrist_candidates':{'left':{'point':(.5,.4),'visibility':.55},'right':{'point':(.5,1.2),'visibility':.9}}}
    assert not analyzer._geometry(PERSON,raw,(400,600))['wrists']
    eating=analyzer._eating_geometry(PERSON,raw,(400,600))
    assert eating['wrists']=={'left':(100,160)}
    assert eating['wrist_quality']['left']==.55


def test_shared_pose_export_keeps_existing_filtered_wrists_unchanged():
    import numpy as np
    from types import SimpleNamespace
    from unittest.mock import Mock
    from ai_engine.classroom.face_pose_analyzer import FacePoseAnalyzer
    model=FacePoseAnalyzer.__new__(FacePoseAnalyzer);model.camera_id='fixture';model._face_mesh=None;model._hands=None
    landmarks=[SimpleNamespace(x=.5,y=.4,z=0,visibility=.9) for _ in range(33)]
    landmarks[15].visibility=.55
    model._pose=Mock(process=Mock(return_value=SimpleNamespace(pose_landmarks=SimpleNamespace(landmark=landmarks))))
    raw=model.analyze_crop(np.zeros((400,200,3),np.uint8))
    assert 'left' not in raw['wrists'] and 'right' in raw['wrists']
    assert raw['eating_wrist_candidates']['left']['visibility']==.55
    model._pose.process.assert_called_once()
