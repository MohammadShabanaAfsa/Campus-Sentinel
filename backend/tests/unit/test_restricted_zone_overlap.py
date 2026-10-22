import pytest
from ai_engine.behavioral.zone_checker import ZoneChecker
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions

def rectangle(a,b,c,d):return [{'x':a,'y':b},{'x':c,'y':b},{'x':c,'y':d},{'x':a,'y':d}]

@pytest.mark.parametrize('polygon,expected',[
    (rectangle(.7,.2,.9,.8),0), # Entire person outside.
    (rectangle(.56,.1,.8,.9),.10), # Side of bbox enters.
    (rectangle(.1,.1,.7,.3),1/6), # Upper body only.
    (rectangle(.1,.7,.7,.9),1/6), # Lower body only.
    (rectangle(.5,.7,.7,.9),1/24), # Corner overlap too small: do not bypass area threshold.
    (rectangle(.1,.45,.9,.55),1/6), # Crossing edges: no bbox corners inside polygon.
    (rectangle(.599,.1,.8,.9),.0025), # Tiny sliver rejected.
    (rectangle(.58,.1,.8,.9),.05), # Threshold boundary.
])
def test_exact_overlap_area(polygon,expected):
    saved=[dict(p) for p in polygon]
    ratio=ZoneChecker.overlap_ratio([200,200,600,800],1000,1000,polygon)
    assert ratio==pytest.approx(expected) and polygon==saved

def test_concave_disconnected_intersection_and_orientation():
    polygon=[{'x':0,'y':0},{'x':1,'y':0},{'x':1,'y':1},{'x':.8,'y':1},
             {'x':.8,'y':.2},{'x':.2,'y':.2},{'x':.2,'y':1},{'x':0,'y':1}]
    assert ZoneChecker.overlap_ratio([0,300,1000,800],1000,1000,polygon)==pytest.approx(.4)
    assert ZoneChecker.overlap_ratio([0,300,1000,800],1000,1000,list(reversed(polygon)))==pytest.approx(.4)

@pytest.mark.parametrize('camera',['entrance','classroom'])
def test_overlap_episode_entry_stay_exit_reentry(monkeypatch,camera):
    monkeypatch.setattr(ZoneChecker,'_load_zones',lambda self:None)
    obj=ZoneChecker(camera);obj._zones=[{'id':'zone','camera_id':camera,'name':'Area','alert_level':'high','points':rectangle(.5,.2,.7,.8)}]
    router=ConfirmedAlertTransitions();episodes=[]
    for stamp,left in enumerate([100,400,400,100,400]):
        t={'track_id':1,'class_name':'person','bbox':[left,200,left+200,800],'time_since_update':0}
        alerts=obj.analyze([t],1000,1000)
        assert len(alerts)==(1 if stamp in (1,4) else 0)
        routed=router.update(obj.overlay_events,[t],now=stamp)
        assert len(routed)==len(alerts)
        if routed:episodes.append(routed[0]['metadata']['episode_id'])
    assert len(set(episodes))==2

def test_corner_containment_scaling_and_degenerate_bbox():
    polygon=rectangle(.1,.1,.8,.8)
    assert ZoneChecker.overlap_ratio([0,0,500,500],1000,1000,polygon)==pytest.approx(.64)
    assert ZoneChecker.overlap_ratio([0,0,50,50],100,100,polygon)==pytest.approx(.64)
    assert ZoneChecker.overlap_ratio([1,1,1,2],100,100,polygon)==0
