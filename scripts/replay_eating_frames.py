"""Replay saved camera frames for eating only; never publish or save alerts."""
import argparse,json,os,sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--camera',choices=['entrance','classroom'],default='entrance')
parser.add_argument('--prefix',default='eating-repaired')
args=parser.parse_args()
os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
import cv2
from app.core.config import settings
from ai_engine.behavioral.person_activity import PersonActivityAnalyzer
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions
config=settings.model_copy(update={'ACTIVITY_DEBUG':False,'EATING_DEBUG':False,'PHONE_EATING_DEBUG':False})
directory=ROOT/'logs/phone-eating-repair';records=[];seen=set();session=None;analyzer=None;router=None;alert_count=0
for path in sorted(directory.glob(f'{args.prefix}-{args.camera}-[0-9][0-9].jpg')):
    metadata=json.loads(path.with_suffix('.json').read_text())
    key=(metadata['stream_session'],metadata['frame_number'])
    if key in seen:continue
    seen.add(key)
    if session!=key[0]:
        session=key[0];analyzer=PersonActivityAnalyzer('saved-eating-'+args.camera,config);router=ConfirmedAlertTransitions()
    frame=cv2.imread(str(path))
    if frame is None:raise ValueError('Unreadable saved frame '+str(path))
    stamp=datetime.fromisoformat(metadata['timestamp'].replace('Z','+00:00')).timestamp()
    tracks=metadata['tracks'];signals=analyzer.sample(frame,tracks)
    events=analyzer.analyze(tracks,[],signals,frame.shape,now=stamp)
    alert_count+=len(router.update(events,tracks,now=stamp))  # Local calculation only, never dispatched.
    for track in tracks:
        if track.get('class_name')!='person' or track.get('time_since_update',0)>0:continue
        tid=track['track_id'];raw=signals.get(tid,{});g=analyzer._eating_geometry(track,raw,frame.shape);eat=analyzer.eating.get(tid)
        records.append({'frame':path.name,'timestamp':stamp,'track_id':tid,
            'mouth_available':g['mouth'] is not None,'shoulders_available':len(g['shoulders'])==2,
            'wrist_visibility':raw.get('landmark_visibility',{}),'wrist_sources':g['wrist_sources'],'accepted_wrist_visibility':g['wrist_quality'],
            'normalized_distances':{side:__import__('math').dist(point,g['mouth'])/g['scale'] for side,point in g['wrists'].items()} if g['mouth'] and g['scale']>=10 else {},
            'selected_hand':eat.selected_wrist if eat else None,'phases':{side:h['phase'] for side,h in eat.hands.items()} if eat else {},
            'completed_cycles':len(eat.events) if eat else 0,'confirmed':any(e['type']=='eating' and e['track_id']==tid for e in events)})
report={'camera':args.camera,'mode':'offline saved-frame replay; no database or Redis writes',
    'near':config.EATING_MOUTH_DISTANCE_THRESHOLD,'away':config.EATING_AWAY_DISTANCE_THRESHOLD,
    'required_cycles':config.EATING_MIN_EVENTS,'window_seconds':config.EATING_WINDOW_SECS,'samples':records,
    'max_cycles':max((r['completed_cycles'] for r in records),default=0),'confirmed_samples':sum(r['confirmed'] for r in records),'local_alert_transitions':alert_count}
report['test_min_cycles']=config.EATING_TEST_MIN_CYCLES
report['test_cycle_met']=report['max_cycles']>=config.EATING_TEST_MIN_CYCLES
destination=directory/f'eating-only-replay-{args.camera}.json';destination.write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='samples'}))
