from types import SimpleNamespace
from unittest.mock import Mock,AsyncMock
import uuid
import pytest
from ai_engine.behavioral.fall import FallDetector
from ai_engine.behavioral.zone_checker import ZoneChecker
from ai_engine.vision.vehicle_counter import VehicleCounter
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions
from app.schemas.camera import CountingLine,RestrictedZoneCreate

LINE={'points':[{'x':.1,'y':.5},{'x':.9,'y':.5}],'enabled':True}

def vehicle(y,kind='car',tid=1,x=.5,stale=0,size=100):
    return {'track_id':tid,'class_name':kind,'time_since_update':stale,
            'bbox':[x*size-5,y*size-5,x*size+5,y*size+5],'confidence':.9}

@pytest.mark.parametrize('kind',['car','motorcycle','bicycle','bus','truck'])
def test_vehicle_crossing_in_out_and_dedup(kind):
    counter=VehicleCounter();counter.configure(LINE)
    assert counter.update([vehicle(.3,kind)],(100,100))['total']==0
    assert counter.update([vehicle(.4,kind)],(100,100))['total']==0
    assert counter.update([vehicle(.7,kind)],(100,100))['in']==1
    assert counter.update([vehicle(.8,kind)],(100,100))['total']==1
    assert counter.update([vehicle(.3,kind)],(100,100))['out']==1
    assert counter.update([vehicle(.7,kind)],(100,100))['total']==2

def test_vehicle_no_line_stale_person_or_beyond_segment():
    counter=VehicleCounter()
    assert counter.update([vehicle(.7)],(100,100)) is None
    counter.configure(LINE)
    for track in [vehicle(.3,x=.99),vehicle(.7,x=.99),vehicle(.3,'person'),vehicle(.7,'person'),vehicle(.3,stale=1),vehicle(.7,stale=1)]:
        assert counter.update([track],(100,100))['total']==0

def test_vehicle_resolution_independence_deadband_and_reset():
    counter=VehicleCounter();counter.configure(LINE)
    counter.update([vehicle(.3,size=1000)],(1000,1000))
    counter.update([vehicle(.501,size=1000)],(1000,1000))
    assert counter.update([vehicle(.7,size=1000)],(1000,1000))['in']==1
    counter.configure({**LINE,'enabled':False})
    assert counter.update([], (1000,1000)) is None
    counter.configure(LINE)
    assert counter.update([], (1000,1000))['total']==0

def pose(horizontal=False):
    return ({'left_shoulder':(.2,.45),'right_shoulder':(.2,.55),'left_hip':(.8,.45),'right_hip':(.8,.55)}
            if horizontal else {'left_shoulder':(.4,.2),'right_shoulder':(.6,.2),'left_hip':(.4,.7),'right_hip':(.6,.7)})

def fall_sample(det,stamp,horizontal=False,aspect=None):
    bbox=[100,100,200,500] if not horizontal else [100,500,700,800]
    if aspect is not None:bbox=[100,500,100+300*aspect,800]
    track={'track_id':7,'class_name':'person','bbox':bbox,'time_since_update':0}
    return det.analyze([track],{7:{'fall_pose':pose(horizontal),'analysis_bbox':bbox}},(1000,1000),now=stamp)

@pytest.fixture
def fall():return FallDetector(SimpleNamespace(FALL_ANGLE_THRESHOLD=60,FALL_PERSISTENCE_SECS=4,FALL_RECOVERY_SECS=2))

def test_fall_sudden_transition_persistence_recovery_and_one_alert(fall):
    assert fall_sample(fall,0)==[]
    for stamp in (1,2,3,4):assert fall_sample(fall,stamp,True)==[]
    events=fall_sample(fall,5,True)
    assert events==[{'type':'fall_detected','severity':'high','track_id':7}]
    router=ConfirmedAlertTransitions();track={'track_id':7,'class_name':'person'}
    assert len(router.update(events,[track],now=5))==1
    assert router.update(fall_sample(fall,6,True),[track],now=6)==[]
    assert fall_sample(fall,7) # Recovery requires sustained upright evidence.
    assert fall_sample(fall,9)==[] and fall.states[7]['phase']=='NORMAL'

def test_fall_upright_sitting_bending_brief_and_slow_lying_not_confirmed(fall):
    for stamp in range(5):assert fall_sample(fall,stamp)==[]
    assert fall_sample(fall,5,False,aspect=1.2)==[] # Upright torso while sitting.
    assert fall_sample(fall,6,True,aspect=.4)==[] # Narrow bbox while bending.
    assert fall_sample(fall,7)==[]
    assert fall_sample(fall,8,True)==[]
    assert fall_sample(fall,9)==[] # Brief horizontal posture.
    for stamp in range(13,20):assert fall_sample(fall,stamp,True)==[] # No sudden transition.

def test_fall_pose_required_and_track_expiry(fall):
    fall_sample(fall,0)
    track={'track_id':7,'class_name':'person','bbox':[100,500,700,800]}
    assert fall.analyze([track],{},(1000,1000),now=1)==[]
    fall.analyze([],{},(1000,1000),now=5)
    assert fall.states=={}


def test_supported_crouch_or_shoe_tying_is_not_a_fall(fall):
    fall_sample(fall,0)
    bbox=[100,500,700,800]
    raw=pose(True);raw.update(left_knee=(.75,.95),right_knee=(.85,.95))
    for stamp in range(1,8):
        assert fall.analyze([{'track_id':7,'class_name':'person','bbox':bbox}],
                            {7:{'fall_pose':raw,'analysis_bbox':bbox}},(1000,1000),now=stamp)==[]

def test_zone_foot_point_normalization_enter_exit_reenter(monkeypatch):
    monkeypatch.setattr(ZoneChecker,'_load_zones',lambda self:None)
    checker=ZoneChecker('fixture')
    assert checker.analyze([vehicle(.7,'person')],100,100)==[]
    checker._zones=[{'id':'z','name':'Area','alert_level':'high',
                     'points':[{'x':.2,'y':.6},{'x':.8,'y':.6},{'x':.8,'y':.95},{'x':.2,'y':.95}]}]
    outside=vehicle(.3,'person');inside=vehicle(.7,'person')
    assert checker.analyze([outside],100,100)==[]
    assert len(checker.analyze([inside],100,100))==1
    assert checker.overlay_events[0]['track_id']==1
    assert checker.analyze([inside],100,100)==[]
    assert checker.analyze([outside],100,100)==[]
    assert len(checker.analyze([inside],100,100))==1
    second=ZoneChecker('other-camera')
    assert second.analyze([inside],100,100)==[]

def test_geometry_validation():
    assert CountingLine(**LINE).points==LINE['points']
    with pytest.raises(ValueError):CountingLine(points=[{'x':20,'y':0},{'x':1,'y':1}])
    with pytest.raises(ValueError):CountingLine(points=[{'x':0,'y':0},{'x':0,'y':0}])
    with pytest.raises(ValueError):RestrictedZoneCreate(name='bad',zone_points=[{'x':0,'y':0}]*3)
    data=RestrictedZoneCreate(name='Area',zone_points=[{'x':0,'y':0},{'x':1,'y':0},{'x':1,'y':1}])
    assert data.is_active and data.alert_level=='high'

@pytest.mark.asyncio
async def test_counting_line_api_preserves_other_camera_config():
    from app.api.v1.endpoints.cameras import save_counting_line,clear_counting_line
    camera=SimpleNamespace(config={'classroom_enabled':True,'other':'preserved'})
    db=SimpleNamespace(get=AsyncMock(return_value=camera),commit=AsyncMock())
    cid=uuid.uuid4()
    await save_counting_line(cid,CountingLine(**LINE),db,None)
    assert camera.config['vehicle_counting_line']==LINE and camera.config['other']=='preserved'
    await clear_counting_line(cid,db,None)
    assert camera.config=={'classroom_enabled':True,'other':'preserved'}

@pytest.mark.asyncio
async def test_zone_edit_clear_camera_scoping():
    from app.api.v1.endpoints.cameras import edit_zone,clear_zone
    from fastapi import HTTPException
    cid=uuid.uuid4();zid=uuid.uuid4();zone=SimpleNamespace(camera_id=cid,is_active=True)
    db=SimpleNamespace(get=AsyncMock(return_value=zone),commit=AsyncMock(),refresh=AsyncMock(),delete=AsyncMock())
    data=RestrictedZoneCreate(name='Area',zone_points=[{'x':0,'y':0},{'x':1,'y':0},{'x':1,'y':1}])
    await edit_zone(cid,zid,data,db,None)
    assert zone.zone_points==data.zone_points
    with pytest.raises(HTTPException):await clear_zone(uuid.uuid4(),zid,db,None)
    await clear_zone(cid,zid,db,None)
    db.delete.assert_awaited_once_with(zone)
