"""Short labeled EAR capture from existing Redis frames; no production changes."""
import os,sys,json,time,base64,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
import cv2,numpy as np,redis
from app.core.config import settings
from ai_engine.classroom.face_pose_analyzer import FacePoseAnalyzer
parser=argparse.ArgumentParser();parser.add_argument('--label',required=True,choices=['open','closed']);parser.add_argument('--seconds',type=float,default=15)
args=parser.parse_args()
r=redis.from_url(settings.REDIS_URL);cid='1a32cb23-0820-4385-9ab5-de8e472e2c04'
analyzer=FacePoseAnalyzer.get_instance('calibration')
samples=[];start=time.time();last_frame=None
print('Eye capture started: '+args.label,flush=True)
while time.time()-start<args.seconds:
    raw=r.get(f'camera:{cid}:latest_frame');payload=r.get(f'camera:{cid}:tracks')
    if raw and payload:
        data=json.loads(payload);frame_id=(data.get('stream_session'),data.get('frame_number'))
        persons=[t for t in data['tracks'] if t.get('class_name')=='person' and t.get('time_since_update',0)==0]
        if persons and frame_id!=last_frame:
            last_frame=frame_id;track=max(persons,key=lambda t:(t['bbox'][2]-t['bbox'][0])*(t['bbox'][3]-t['bbox'][1]))
            frame=cv2.imdecode(np.frombuffer(base64.b64decode(raw),np.uint8),cv2.IMREAD_COLOR);h,w=frame.shape[:2]
            a,b,c,d=track['bbox'];dx,dy=.2*(c-a),.2*(d-b)
            a,b,c,d=max(0,int(a-dx)),max(0,int(b-dy)),min(w,int(c+dx)),min(h,int(d+dy))
            signals=analyzer.analyze_crop(frame[b:d,a:c])
            samples.append({'time':time.time(),'track_id':track['track_id'],'frame_number':data['frame_number'],'ear':signals['ear'],'face_detected':signals['face_detected']})
    time.sleep(.5)
values=[s['ear'] for s in samples if s['ear'] is not None]
report={'label':args.label,'samples':samples,'valid_samples':len(values),'minimum':min(values) if values else None,'mean':float(np.mean(values)) if values else None,'maximum':max(values) if values else None}
(ROOT/f'logs/eye-calibration-{args.label}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='samples'}))
