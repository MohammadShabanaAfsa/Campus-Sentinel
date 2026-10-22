"""Read-only camera routing, processed FPS and service health observation."""
import base64,json,os,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
from sqlalchemy import create_engine,text
from app.core.config import settings
from app.core.security import create_access_token
import redis,cv2,numpy as np
engine=create_engine(settings.SYNC_DATABASE_URL,pool_pre_ping=True)
with engine.connect() as c:
 user=c.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar_one()
 cameras=c.execute(text('SELECT id,name,zone_type,status,config FROM cameras WHERE is_active=true ORDER BY name')).mappings().all()
 remaining=c.execute(text("SELECT count(*) FROM cameras WHERE name LIKE 'Software validation %'")).scalar_one()
headers={'Authorization':'Bearer '+create_access_token(str(user))}
def api(path):
 with urllib.request.urlopen(urllib.request.Request('http://localhost:8000'+path,headers=headers),timeout=10) as response:return json.load(response)
r=redis.Redis.from_url(settings.REDIS_URL,decode_responses=True)
for _ in range(20):
 status=api('/api/v1/streams/status')
 if any(value.get('state')=='running' and value.get('frames_processed',0)>=10 for value in status.values()):break
 time.sleep(1)
start=api('/api/v1/streams/status');stamp=time.monotonic();time.sleep(10);finish=api('/api/v1/streams/status');elapsed=time.monotonic()-stamp
report={'method':'LIVE connectivity/frame/YOLO-track/health observation only','seconds':elapsed,'redis_ping':r.ping(),'fixture_cameras_remaining':remaining,'backend_health':api('/health'),'cameras':[]}
for camera in cameras:
 cid=str(camera['id']);current=finish.get(cid,{});before=start.get(cid,{});data=json.loads(r.get(f'camera:{cid}:tracks') or '{}');encoded=r.get(f'camera:{cid}:latest_frame');frame=cv2.imdecode(np.frombuffer(base64.b64decode(encoded),np.uint8),cv2.IMREAD_COLOR) if encoded else None
 config=camera['config'] or {};campus=config.get('campus_events') or {};classroom=camera['zone_type']=='classroom'
 report['cameras'].append({'camera_id':cid,'name':camera['name'],'role':camera['zone_type'],'state':current.get('state'),'error':current.get('last_error'),'frame_delivered':frame is not None,'frame_shape':list(frame.shape) if frame is not None else None,'processed_fps':round((current.get('frames_processed',0)-before.get('frames_processed',0))/elapsed,3) if current.get('state')=='running' else None,'current_detections':data.get('detection_count'),'active_track_ids':[t['track_id'] for t in data.get('tracks',[]) if t.get('time_since_update',0)==0], 'routing':{'person_activity':classroom or (camera['zone_type']=='general' and settings.ENABLE_ACTIVITY_ANALYSIS_ON_GENERAL),'movement':True,'restricted':True,'fall':True,'fight':True,'bag':True,'crowd':not classroom,'loitering':not classroom,'classroom_metrics':classroom,'qr':settings.QR_IDENTIFICATION_ENABLED,'vehicle_line_configured':bool(config.get('vehicle_counting_line')),'after_hours_configured':bool((campus.get('schedule') or {}).get('enabled')),'emergency_exit_zones':len([z for z in campus.get('exit_zones',[]) if z.get('enabled',True)])}})
from app.core.celery_app import celery_app
report['celery_ping']=celery_app.control.inspect(timeout=3).ping()
with urllib.request.urlopen('http://localhost:3000',timeout=10) as response:report['frontend_http']=response.status
report['production_settings']={key:getattr(settings,key) for key in ['ACTIVITY_DEBUG','FRAME_SKIP','LOITERING_THRESHOLD_SECS','LOITERING_MOVEMENT_RADIUS','LOITERING_TRACK_GRACE_SECS','ABANDONED_BAG_SECS','FIGHT_PERSISTENCE_SECS','FALL_PERSISTENCE_SECS']}
(ROOT/'logs/stabilization-health.json').write_text(json.dumps(report,indent=2,default=str));print(json.dumps(report,default=str));r.close();engine.dispose()
