"""Classroom metrics regression using synthetic tracks and actual timestamps."""
from ai_engine.classroom.attendance import AttendanceAnalyzer
from ai_engine.classroom.engagement import FacultyEngagementAnalyzer
from ai_engine.classroom.attention_index import compute_attention_index
from ai_engine.classroom.classroom_monitor import ClassroomMonitor

def test_missing_students_requires_sustained_shortfall_and_is_camera_local(monkeypatch):
 import ai_engine.classroom.attendance as module
 clock=[0.0];monkeypatch.setattr(module.time,'time',lambda:clock[0])
 a,b=AttendanceAnalyzer('A'),AttendanceAnalyzer('B')
 track={'class_name':'person','track_id':1}
 assert not a.analyze([track],3)['alerts']
 clock[0]=19;assert not a.analyze([track],3)['alerts']
 clock[0]=20;assert a.analyze([track],3)['alerts'][0]['alert_type']=='missing_students'
 assert not a.analyze([track],3)['alerts']
 assert b._state.shortfall_since is None
 assert a.analyze([track]*3,3)['overlay_events']==[]

def test_faculty_engagement_state_and_cleanup_are_camera_local(monkeypatch):
 import ai_engine.classroom.engagement as module
 clock=[1.0];monkeypatch.setattr(module.time,'time',lambda:clock[0])
 a,b=FacultyEngagementAnalyzer('A'),FacultyEngagementAnalyzer('B')
 track={'track_id':1,'class_name':'person','cx':320,'cy':100,'duration_secs':10}
 for stamp in range(2,8):
  clock[0]=stamp;result=a.analyze([track],None,{'facing_camera':True},640,480)
 assert result['faculty_present'] and result['faculty_track_id']==1
 assert 0<=result['engagement_score']<=100 and a._positions[1]
 assert not b._positions
 a.cleanup(set());assert not a._positions

def test_cai_is_bounded_and_responds_to_confirmed_distraction():
 full=compute_attention_index(20,20,0,0,100,True)
 low=compute_attention_index(20,20,10,10,0,True)
 assert full['attention_index']==100 and full['attentive_count']==20
 assert low['attention_index']==25 and low['attentive_count']==0

def test_low_attention_and_engagement_require_sustained_evidence(monkeypatch):
 import ai_engine.classroom.classroom_monitor as module
 clock=[0.0];monkeypatch.setattr(module.time,'time',lambda:clock[0])
 a=ClassroomMonitor.__new__(ClassroomMonitor);a.camera_id='classroom'
 a._low_attention_since=a._low_engagement_since=None
 a._low_attention_confirmed=a._low_engagement_confirmed=False
 engagement={'faculty_present':True,'engagement_score':10,'details':{}}
 assert not a._sustained_attention_alert({'attention_index':20,'level':'poor'})
 assert not a._sustained_engagement_alert(engagement)
 clock[0]=31
 assert a._sustained_attention_alert({'attention_index':20,'level':'poor'})[0]['alert_type']=='low_class_attention'
 assert a._sustained_engagement_alert(engagement)[0]['alert_type']=='low_faculty_engagement'
 a._sustained_attention_alert({'attention_index':90})
 a._sustained_engagement_alert({**engagement,'engagement_score':90})
 assert not a._low_attention_confirmed and not a._low_engagement_confirmed
