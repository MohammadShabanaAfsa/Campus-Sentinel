from types import SimpleNamespace
import pytest
from ai_engine.behavioral.person_activity import PersonActivityAnalyzer
from ai_engine.vision.detector import YOLODetector


def settings(**updates):
    values=dict(ACTIVITY_ANALYSIS_INTERVAL_SECS=.75,ACTIVITY_DEBUG=False,PHONE_USE_MIN_DURATION_SECS=2,
        PHONE_USE_MIN_HITS=3,PHONE_USE_CLEAR_TIMEOUT_SECS=1.5,PHONE_PERSON_ASSOCIATION_MARGIN=20,
        PHONE_HAND_DISTANCE_THRESHOLD=.45,EATING_MIN_EVENTS=3,EATING_WINDOW_SECS=20,
        EATING_CLEAR_TIMEOUT_SECS=6,EATING_MOUTH_DISTANCE_THRESHOLD=.35,EATING_MIN_NEAR_SECS=.25,
        EATING_MAX_NEAR_SECS=3,EATING_MIN_EVENT_INTERVAL_SECS=1)
    return SimpleNamespace(**{**values,**updates})


def person(tid=12,x=0):
    return dict(track_id=tid,class_name='person',bbox=[x,0,x+200,400],time_since_update=0)


def signals(wrist=(.5,.4),elbow=(.5,.55),face=True):
    return dict(face_detected=face,mouth_center=(.5,.2),wrists={'left':wrist},
        elbows={'left':elbow},shoulders={'left':(.25,.3),'right':(.75,.3)})


def phone(x=100,y=160):
    return dict(class_name='cell phone',class_id=67,confidence=.9,bbox=[x-10,y-15,x+10,y+15])


def run(analyzer,now,raw=None,detections=None,tracks=None):
    return analyzer.analyze(tracks or [person()],detections or [],{12:raw or signals()},(400,600,3),now=now)


def test_coco_phone_class_is_retained():
    assert YOLODetector.TARGET_CLASSES[67]=='cell phone'


def test_sleep_grace_pauses_unknown_time_and_keeps_full_duration(monkeypatch):
    import ai_engine.classroom.student_state as rules
    clock=[100.0];monkeypatch.setattr(rules.time,'time',lambda:clock[0])
    detector=rules.SleepingDetector('camera')
    closed={'ear':.1,'face_detected':True}
    detector.update(12,closed)
    clock[0]=110;assert detector.update(12,closed)['duration_secs']==10
    clock[0]=111;missing=detector.update(12,{})
    assert missing['duration_secs']==10 and not missing['is_sleeping']
    assert detector.diagnostics[12]['reset_reason']=='landmarks_missing_grace_paused'
    clock[0]=112;assert detector.update(12,closed)['duration_secs']==10
    clock[0]=117;assert detector.update(12,closed)['is_sleeping']
    clock[0]=118;assert not detector.update(12,{'ear':.3,'face_detected':True})['is_sleeping']
    assert detector._states[12].closed_since is None


def test_sleep_long_landmark_gap_resets_candidate(monkeypatch):
    import ai_engine.classroom.student_state as rules
    clock=[100.0];monkeypatch.setattr(rules.time,'time',lambda:clock[0])
    detector=rules.SleepingDetector('camera')
    detector.update(12,{'ear':.1})
    clock[0]=104;assert detector.update(12,{})['duration_secs']==0
    assert detector.diagnostics[12]['reset_reason']=='landmark_grace_expired'
    clock[0]=105;assert detector.update(12,{'ear':.1})['duration_secs']==0


def test_phone_specific_confidence_preserves_person_cutoff():
    import numpy as np
    from unittest.mock import Mock
    def box(cls,conf):
        return SimpleNamespace(cls=[cls],conf=[conf],xyxy=np.array([[10,20,30,40]]))
    detector=YOLODetector.__new__(YOLODetector)
    detector.conf_threshold=.5;detector.phone_conf_threshold=.25
    detector._model=Mock(return_value=[SimpleNamespace(boxes=[box(67,.30),box(0,.30),box(0,.90)])])
    result=detector.detect(np.zeros((100,100,3),np.uint8))
    assert [(d['class_id'],d['confidence']) for d in result]==[(67,.30),(0,.90)]
    assert detector._model.call_args.kwargs['conf']==.25
    assert 0 in detector._model.call_args.kwargs['classes'] and 67 in detector._model.call_args.kwargs['classes']


def test_phone_roi_returns_original_frame_coordinates():
    import numpy as np
    from unittest.mock import Mock
    detector=YOLODetector.__new__(YOLODetector);detector.phone_conf_threshold=.25
    box=SimpleNamespace(cls=[67],conf=[.4],xyxy=np.array([[64,128,128,192]],dtype=float))
    detector._model=Mock(return_value=[SimpleNamespace(boxes=[box])])
    result=detector.detect_phone_rois(np.zeros((400,600,3),np.uint8),[person()])
    assert result[0]['class_id']==67 and result[0]['source']=='person_roi'
    assert detector._model.call_args.kwargs['classes']==[67]
    assert detector._model.call_args.kwargs['imgsz']>=max(detector._model.call_args.args[0].shape[:2])
    assert all(0<=v<=600 for v in result[0]['bbox'])
    detector.conf_threshold=.5
    detector.detect(np.zeros((400,600,3),np.uint8))
    assert 0 in detector._model.call_args.kwargs['classes']  # Restore class filter after phone-only ROI.
    assert detector._model.call_args.kwargs['imgsz']==640


def test_roi_recovery_does_not_require_landmarks_and_skips_detected_phone():
    from unittest.mock import Mock
    import numpy as np
    detector=YOLODetector.__new__(YOLODetector);detector.phone_conf_threshold=.25
    detector.detect_phone_rois=Mock(return_value=[phone()])
    cfg=settings(PHONE_ROI_INFERENCE_ENABLED=True,PHONE_ROI_MAX_PERSONS=2)
    image=np.zeros((400,600,3),np.uint8)
    assert detector.activity_phone_candidates(image,[person()],[],cfg)==[phone()]
    assert detector.last_phone_roi_used
    detector.detect_phone_rois.reset_mock()
    assert detector.activity_phone_candidates(image,[person()],[phone()],cfg)==[phone()]
    detector.detect_phone_rois.assert_not_called()
    assert not detector.last_phone_roi_used


def test_large_person_roi_keeps_enlarged_network_input():
    from unittest.mock import Mock
    import numpy as np
    detector=YOLODetector.__new__(YOLODetector);detector.phone_conf_threshold=.25
    detector._model=Mock(return_value=[])
    detector.detect_phone_rois(np.zeros((480,640,3),np.uint8),[{**person(),'bbox':[50,0,590,480]}])
    call=detector._model.call_args
    assert call.kwargs['imgsz']>640
    assert call.kwargs['imgsz']>=max(call.args[0].shape[:2])
    assert call.kwargs['imgsz']<=1280


def test_tall_chest_phone_matches_visible_supporting_wrist_without_elbow():
    analyzer=PersonActivityAnalyzer('camera',settings())
    raw=signals(wrist=(.6,.5));raw['elbows']={}
    # The hand contacts the lower edge; distance to center alone is misleading.
    large_phone={**phone(),'bbox':[105,80,140,210]}
    for now in (0,1,2):result=run(analyzer,now,raw,[large_phone])
    assert result==[dict(type='phone_use',severity='low',track_id=12)]
    assert analyzer.phone_observations[12][0]['associated_track_id']==12


def test_desk_phone_near_resting_hand_still_does_not_confirm():
    analyzer=PersonActivityAnalyzer('camera',settings())
    raw=signals(wrist=(.5,.7));raw['elbows']={}
    desk={**phone(),'bbox':[80,240,120,290]}
    for now in (0,1,2,3):assert run(analyzer,now,raw,[desk])==[]


def test_eating_prefers_better_visible_wrist_and_accepts_right_only():
    analyzer=PersonActivityAnalyzer('camera',settings())
    for start in (0,2,4):
        for now,y in ((start,.5),(start+.75,.24),(start+1.5,.5)):
            raw=signals();raw['wrists']={'right':(.5,y)}
            raw['landmark_visibility']={'right_wrists':{'visibility':.8}}
            result=run(analyzer,now,raw)
    assert analyzer.eating[12].selected_wrist=='right'
    assert any(e['type']=='eating' for e in result)
    raw=signals();raw['wrists']['right']=(.5,.5)
    raw['landmark_visibility']={'left_wrists':{'visibility':.65},'right_wrists':{'visibility':.9}}
    run(analyzer,8,raw)
    assert analyzer.eating[12].selected_wrist=='right'


def test_eating_does_not_accept_effectively_absent_wrist():
    analyzer=PersonActivityAnalyzer('camera',settings(EATING_WRIST_VISIBILITY_THRESHOLD=.6))
    raw=signals();raw['landmark_visibility']={'left_wrists':{'visibility':.2}}
    run(analyzer,0,raw)
    assert analyzer.eating[12].selected_wrist is None
    assert not analyzer.eating[12].hands


def test_eating_short_gap_pauses_near_dwell_but_can_resume_observed_cycle():
    analyzer=PersonActivityAnalyzer('camera',settings())
    run(analyzer,0,signals(wrist=(.5,.5)))
    run(analyzer,.75,signals(wrist=(.5,.24)))
    run(analyzer,1,dict(face_detected=False,wrists={},shoulders={}))
    run(analyzer,1.5,signals(wrist=(.5,.24)))
    assert analyzer.eating[12].hands['left']['near_since']==1.5  # Unknown time starts at the last valid sample.
    run(analyzer,2,signals(wrist=(.5,.5)))
    assert len(analyzer.eating[12].events)==1


def test_better_visible_resting_hand_does_not_hide_other_hands_cycles():
    analyzer=PersonActivityAnalyzer('camera',settings())
    for start in (0,2,4):
        for now,y in ((start,.5),(start+.75,.24),(start+1.5,.5)):
            raw=signals(wrist=(.5,.5));raw['wrists']['right']=(.5,y)
            raw['landmark_visibility']={'left_wrists':{'visibility':.99},'right_wrists':{'visibility':.8}}
            result=run(analyzer,now,raw)
    assert len(analyzer.eating[12].events)==3
    assert any(e['type']=='eating' for e in result)


def test_valid_slower_samples_do_not_erase_an_observed_cycle():
    analyzer=PersonActivityAnalyzer('camera',settings())
    run(analyzer,0,signals(wrist=(.5,.5)))
    run(analyzer,1.7,signals(wrist=(.5,.24)))
    run(analyzer,3.4,signals(wrist=(.5,.5)))
    assert len(analyzer.eating[12].events)==1


def test_calibrated_contact_distance_requires_three_actual_returns_away():
    cfg=settings(EATING_MOUTH_DISTANCE_THRESHOLD=.70,EATING_AWAY_DISTANCE_THRESHOLD=.85)
    analyzer=PersonActivityAnalyzer('camera',cfg)
    for start in (0,3,6):
        run(analyzer,start,signals(wrist=(.5,.47)))  # 1.08 shoulder widths, away.
        run(analyzer,start+1,signals(wrist=(.5,.3375)))  # .55 widths, observed contact.
        result=run(analyzer,start+2,signals(wrist=(.5,.47)))
        assert bool(result)==(start==6)
    assert analyzer.eating[12].events==__import__('collections').deque([2,5,8])


@pytest.mark.parametrize('mode',['one_touch','scratch_once','resting_chin'])
def test_calibrated_distance_does_not_confirm_single_or_held_face_contact(mode):
    analyzer=PersonActivityAnalyzer('camera',settings(EATING_MOUTH_DISTANCE_THRESHOLD=.70,EATING_AWAY_DISTANCE_THRESHOLD=.85))
    run(analyzer,0,signals(wrist=(.5,.47)))
    for now in range(1,8 if mode=='resting_chin' else 2):
        assert run(analyzer,now,signals(wrist=(.5,.3375)))==[]
    assert run(analyzer,8 if mode=='resting_chin' else 2,signals(wrist=(.5,.47)))==[]


def test_limb_geometry_uses_wider_crop_without_moving_face_geometry():
    raw={**signals(),'analysis_bbox':[100,100,300,300],'limb_analysis_bbox':[50,50,350,350]}
    geometry=PersonActivityAnalyzer._geometry(person(),raw,(400,600))
    assert geometry['mouth']==(200,140)
    assert geometry['wrists']['left']==(200,170)


def test_wider_limb_recovery_preserves_face_rule_signals():
    import numpy as np
    class Pose:
        _face_mesh=_pose=object()
        def analyze_crop(self,crop):return {**signals(),'ear':.31,'mar':.04,'head_down':False,'wrists':{}}
        def analyze_activity_limbs(self,crop,threshold):
            assert crop.shape==(340,340,3) and threshold==.5
            return {'wrists':{'right':(.6,.8)},'elbows':{},'shoulders':{'left':(.3,.3),'right':(.7,.3)},
                    'wrist_sources':{'right':'pose'},'landmark_visibility':{'right_wrists':{'visibility':.8}}}
    analyzer=PersonActivityAnalyzer('camera',settings());analyzer._face_pose=Pose()
    raw=analyzer.sample(np.zeros((500,600,3),np.uint8),[{**person(),'bbox':[100,100,300,300]}])[12]
    assert raw['analysis_bbox']==[60,60,340,340]
    assert raw['limb_analysis_bbox']==[30,30,370,370]
    assert (raw['ear'],raw['mar'],raw['head_down'])==(.31,.04,False)


def test_padded_crop_coordinates_and_visibility_are_preserved():
    import numpy as np
    from unittest.mock import Mock
    analyzer=PersonActivityAnalyzer('camera',settings())
    pose=Mock(_face_mesh=object(),_pose=object())
    pose.analyze_crop.return_value={**signals(),'landmark_visibility':{'left_wrists':{'visibility':.4,'in_crop':True}}}
    analyzer._face_pose=pose
    track={**person(),'bbox':[100,100,300,300]}
    raw=analyzer.sample(np.zeros((400,600,3),np.uint8),[track])[12]
    assert raw['analysis_bbox']==[60,60,340,340]
    assert pose.analyze_crop.call_args.args[0].shape==(280,280,3)
    g=analyzer._geometry(track,raw,(400,600))
    assert g['mouth']==(200,116)
    assert raw['landmark_visibility']['left_wrists']['visibility']==.4


def test_general_sleep_talk_use_existing_rules_without_classroom_metrics(monkeypatch):
    import ai_engine.classroom.student_state as rules
    clock = [100.0]
    monkeypatch.setattr(rules.time, 'time', lambda: clock[0])
    analyzer = PersonActivityAnalyzer('entrance', settings(), general_face_activities=True)
    for i in range(25):
        clock[0] = 100.0 + i
        raw = {**signals(), 'ear': .1, 'mar': .1 if i % 2 else .3}
        output = run(analyzer, i, raw)
    assert {'sleeping', 'talking'} <= {e['type'] for e in output}
    assert all(e['track_id'] == 12 for e in output)
    assert analyzer._sleeping.threshold_secs == 15
    assert analyzer._talking.threshold_secs == 8
    analyzer.analyze([], [], {}, (400,600), now=26)
    assert 12 in analyzer._sleeping._states and 12 in analyzer._talking._states
    clock[0]=129
    analyzer.analyze([], [], {}, (400,600), now=29)
    assert analyzer._sleeping._states == analyzer._talking._states == {}


def test_general_opt_out_has_no_sleep_talk_state():
    analyzer = PersonActivityAnalyzer('entrance', settings(), general_face_activities=False)
    assert analyzer._sleeping is None and analyzer._talking is None


def test_debug_snapshot_reports_actual_state_without_advancing_rules(monkeypatch):
    import ai_engine.classroom.student_state as rules
    import ai_engine.behavioral.person_activity as activities
    clock = [100.0]
    monkeypatch.setattr(rules.time, 'time', lambda: clock[0])
    monkeypatch.setattr(activities.time, 'monotonic', lambda: clock[0])
    logged=[]
    monkeypatch.setattr(activities.logger, 'info', logged.append)
    analyzer=PersonActivityAnalyzer('entrance',settings(ACTIVITY_DEBUG=True),True,'General Entrance','general')
    raw={**signals(),'ear':.1,'mar':.2}
    run(analyzer,100,raw)
    analyzer.debug_sample([person()],{12:raw},(400,600),3)
    first=analyzer.debug_snapshots[12]
    assert first['sleeping']['candidate_start_time']==100
    assert first['talking']['mouth_samples']==1
    assert first['talking']['reset_reason']=='insufficient_mouth_samples'
    analyzer.debug_sample([person()],{12:raw},(400,600),6)
    assert analyzer.debug_snapshots[12]['talking']['mouth_samples']==1
    assert not analyzer.debug_snapshots[12]['talking']['updated_this_sample']
    assert analyzer.debug_snapshots[12]['same_track_sample_count']==2
    assert len(logged)==2
    clock[0]=101
    run(analyzer,101,raw)
    analyzer.debug_sample([person()],{12:raw},(400,600),9)
    assert analyzer.debug_snapshots[12]['sleeping']['duration_secs']==1
    assert analyzer.debug_snapshots[12]['talking']['mouth_samples']==2


def test_debug_overlay_is_gated_and_shows_only_one_track(monkeypatch):
    import numpy as np
    import cv2
    analyzer=PersonActivityAnalyzer('entrance',settings(ACTIVITY_DEBUG=True),True)
    tracks=[person(),person(7,250)]
    raw={12:signals(),7:signals()}
    analyzer.analyze(tracks,[],raw,(400,600),now=0)
    analyzer.debug_sample(tracks,raw,(400,600),3)
    texts=[]
    monkeypatch.setattr(cv2,'putText',lambda frame,text,*args: texts.append(text))
    frame=np.zeros((400,600,3),np.uint8)
    analyzer.draw_debug(frame,tracks)
    assert texts[0]=='DEBUG #7'
    assert len(texts)==5 and any(t.startswith('EAT cycles=0/3') for t in texts)
    analyzer.settings.ACTIVITY_DEBUG=False
    texts.clear()
    untouched=np.zeros_like(frame)
    assert not analyzer.draw_debug(untouched,tracks).any()
    assert texts==[]


def test_classroom_debug_reads_retained_face_state_without_extra_updates(monkeypatch):
    import ai_engine.classroom.student_state as rules
    monkeypatch.setattr(rules.time,'time',lambda:100.0)
    sleep,talk=rules.SleepingDetector('classroom'),rules.TalkingDetector('classroom')
    raw={**signals(),'ear':.1,'mar':.2}
    sleep.update(12,raw);talk.update(12,raw)
    monitor=SimpleNamespace(_sleeping=sleep,_talking=talk)
    analyzer=PersonActivityAnalyzer('classroom',settings(ACTIVITY_DEBUG=True))
    analyzer.debug_sample([person()],{12:raw},(400,600),30,monitor)
    analyzer.debug_sample([person()],{12:raw},(400,600),33,monitor)
    diagnostic=analyzer.debug_snapshots[12]
    assert diagnostic['talking']['mouth_samples']==1
    assert not diagnostic['talking']['updated_this_sample']
    assert not sleep._states[12].alerted and not talk._states[12].alerted


@pytest.mark.parametrize('general', [False, True])
def test_persistent_hand_held_phone_confirms_only_correct_track(general):
    analyzer=PersonActivityAnalyzer('camera',settings(), general_face_activities=general)
    assert run(analyzer,0,detections=[phone()],tracks=[person(),person(7,300)])==[]
    assert run(analyzer,1,detections=[phone()],tracks=[person(),person(7,300)])==[]
    events=run(analyzer,2,detections=[phone()],tracks=[person(),person(7,300)])
    assert events==[dict(type='phone_use',severity='low',track_id=12)]
    assert 7 not in analyzer.phones
    assert run(analyzer,4)==[]


@pytest.mark.parametrize('object_detection,raw',[(phone(500,160),signals()),
    (phone(100,260),signals(wrist=(.5,.65))),
    (phone(),dict(face_detected=False,wrists={},shoulders={}))])
def test_far_desk_and_unobserved_hands_do_not_confirm(object_detection,raw):
    analyzer=PersonActivityAnalyzer('camera',settings())
    for now in (0,1,2,3):assert run(analyzer,now,raw,detections=[object_detection])==[]


def test_phone_near_box_can_match_visible_raised_wrist():
    analyzer=PersonActivityAnalyzer('camera',settings())
    for now in (0,1,2):events=run(analyzer,now,signals(wrist=(.95,.4),elbow=(.95,.55)),[phone(210)])
    assert events[0]['type']=='phone_use'


def test_ambiguous_phone_is_not_assigned_to_either_person():
    analyzer=PersonActivityAnalyzer('camera',settings())
    raw={12:signals(wrist=(.75,.4)),7:signals(wrist=(.25,.4))}
    for now in (0,1,2):
        assert analyzer.analyze([person(),person(7,100)],[phone(150)],raw,(400,600),now=now)==[]


def test_single_frame_phone_and_long_gap_do_not_confirm():
    analyzer=PersonActivityAnalyzer('camera',settings())
    assert run(analyzer,0,detections=[phone()])==[]
    assert run(analyzer,2)==[]
    assert run(analyzer,3,detections=[phone()])==[]
    assert analyzer.phones[12].hits==1


def eating_cycle(analyzer,start):
    run(analyzer,start,signals(wrist=(.5,.5)))
    assert run(analyzer,start+.75,signals(wrist=(.5,.24)))==[]
    return run(analyzer,start+1.5,signals(wrist=(.5,.5)))


@pytest.mark.parametrize('general', [False, True])
def test_repeated_complete_cycles_confirm_eating_and_clear_after_inactivity(general):
    analyzer=PersonActivityAnalyzer('camera',settings(), general_face_activities=general)
    assert eating_cycle(analyzer,0)==[]
    assert eating_cycle(analyzer,2)==[]
    events=eating_cycle(analyzer,4)
    assert events==[dict(type='eating',severity='low',track_id=12)]
    assert run(analyzer,12,signals(wrist=(.5,.5)))==[]


@pytest.mark.parametrize('raw',[signals(wrist=(.5,.24)),signals(wrist=(.5,.5)),
    dict(face_detected=True,mouth_center=(.5,.2),mar=.8,wrists={},shoulders={}),signals(face=False)])
def test_resting_chin_talking_or_missing_face_do_not_confirm(raw):
    analyzer=PersonActivityAnalyzer('camera',settings())
    for now in range(10):assert run(analyzer,now,raw)==[]


def test_one_face_touch_not_eating_and_people_have_separate_state():
    analyzer=PersonActivityAnalyzer('camera',settings())
    assert eating_cycle(analyzer,0)==[]
    assert len(analyzer.eating[12].events)==1
    assert analyzer.analyze([person(7)],[],{7:signals(wrist=(.5,.24))},(400,600),now=2)==[]
    assert 12 in analyzer.eating  # Short detection loss retains state without new evidence.
    analyzer.analyze([person(7)],[],{7:signals()},(400,600),now=6)
    assert 12 not in analyzer.eating
    assert len(analyzer.eating[7].events)==0


def test_missing_landmarks_do_not_complete_a_phantom_cycle():
    analyzer=PersonActivityAnalyzer('camera',settings())
    run(analyzer,0,signals(wrist=(.5,.5)))
    run(analyzer,.75,signals(wrist=(.5,.24)))
    run(analyzer,1,dict(face_detected=False,wrists={},shoulders={}))
    run(analyzer,1.5,signals(wrist=(.5,.5)))
    assert not analyzer.eating[12].events


def test_face_pose_exports_visible_mouth_and_wrists_without_identity():
    from unittest.mock import Mock
    import numpy as np
    from ai_engine.classroom.face_pose_analyzer import FacePoseAnalyzer
    face=[SimpleNamespace(x=.5,y=.2) for _ in range(468)]
    pose=[SimpleNamespace(x=.5,y=.4,z=0,visibility=.9) for _ in range(33)]
    pose[11].x=.25;pose[12].x=.75
    pose[16].visibility=.2
    analyzer=FacePoseAnalyzer.__new__(FacePoseAnalyzer);analyzer.camera_id='fixture'
    analyzer._face_mesh=Mock(process=Mock(return_value=SimpleNamespace(multi_face_landmarks=[SimpleNamespace(landmark=face)])))
    analyzer._pose=Mock(process=Mock(return_value=SimpleNamespace(pose_landmarks=SimpleNamespace(landmark=pose))))
    raw=analyzer.analyze_crop(np.zeros((400,200,3),np.uint8))
    assert raw['mouth_center']==(.5,.2) and raw['wrists']=={'left':(.5,.4)}
    assert 'identity' not in raw


def test_phone_and_eating_can_coexist_on_one_track_with_low_severity():
    analyzer=PersonActivityAnalyzer('camera',settings())
    def observe(now,near):
        raw=signals(wrist=(.5,.24) if near else (.5,.5))
        raw['wrists']['right']=(.5,.4);raw['elbows']['right']=(.5,.55)
        return run(analyzer,now,raw,[phone()])
    for start in (0,2,4):
        observe(start,False);observe(start+.75,True);events=observe(start+1.5,False)
    assert {item['type'] for item in events}=={'phone_use','eating'}
    assert all(item['track_id']==12 and item['severity']=='low' for item in events)


def test_debug_disabled_emits_no_activity_diagnostics(monkeypatch):
    import ai_engine.behavioral.person_activity as module
    from unittest.mock import Mock
    debug=Mock();monkeypatch.setattr(module.logger,'debug',debug)
    analyzer=PersonActivityAnalyzer('camera',settings())
    run(analyzer,0,detections=[phone()]);debug.assert_not_called()
