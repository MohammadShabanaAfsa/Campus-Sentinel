"""Observe real General Entrance zone samples and alert delivery; inject nothing."""
import asyncio,base64,json,os,sys,time,argparse
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
from app.core.config import settings
from app.core.security import create_access_token
from sqlalchemy import create_engine,text
import redis,websockets
parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,default=45);args=parser.parse_args()
cid='1a32cb23-0820-4385-9ab5-de8e472e2c04';out=ROOT/'logs/restricted-zone-live';out.mkdir(exist_ok=True)
engine=create_engine(settings.SYNC_DATABASE_URL);r=redis.Redis.from_url(settings.REDIS_URL)
with engine.connect() as c:user=c.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar()
log=ROOT/'logs/backend.log';offset=log.stat().st_size;start=time.time()
async def observe():
    ws_events=[];redis_events=[];frames=[];deadline=time.monotonic()+args.seconds
    pubsub=r.pubsub();pubsub.subscribe('alerts_channel')
    async with websockets.connect('ws://localhost:8000/api/v1/ws/events?token='+create_access_token(str(user)),close_timeout=1) as socket:
        print('Restricted-zone live observer connected.',flush=True);ping=time.monotonic();last=None
        while time.monotonic()<deadline:
            if time.monotonic()-ping>=10:await socket.send('ping');ping=time.monotonic()
            try:
                raw=await asyncio.wait_for(socket.recv(),timeout=.5)
                if raw!='pong':
                    item=json.loads(raw);alert=item.get('alert',{})
                    if item.get('type')=='new_alert' and alert.get('alert_type')=='restricted_zone' and alert.get('camera_id')==cid:ws_events.append(item)
            except asyncio.TimeoutError:pass
            while True:
                message=pubsub.get_message()
                if not message:break
                if message['type']=='message':
                    item=json.loads(message['data']);alert=item.get('alert',{})
                    if alert.get('alert_type')=='restricted_zone' and alert.get('camera_id')==cid:redis_events.append(item)
            raw=r.get(f'camera:{cid}:tracks')
            if raw:
                payload=json.loads(raw);number=(payload.get('stream_session'),payload.get('frame_number'))
                if number!=last:
                    last=number;frames.append(payload)
                    restricted=any(b.get('type')=='restricted_zone' for t in payload.get('tracks',[]) for b in t.get('behaviors',[]))
                    if len(frames)==1 or restricted:
                        frame=r.get(f'camera:{cid}:latest_frame')
                        if frame:(out/f'frame-{len(frames):03}.jpg').write_bytes(base64.b64decode(frame))
    pubsub.close();return ws_events,redis_events,frames
ws_events,redis_events,frames=asyncio.run(observe());end=time.time();samples=[]
with log.open('rb') as f:f.seek(offset);lines=f.read().decode('utf-8',errors='replace').splitlines()
for line in lines:
    if 'RESTRICTED_ZONE_SAMPLE {' in line:
        sample,_=json.JSONDecoder().raw_decode(line.split('RESTRICTED_ZONE_SAMPLE ',1)[1])
        if sample['camera_id']==cid:samples.append(sample)
with engine.connect() as c:
    alerts=c.execute(text("SELECT id,title,severity,metadata,created_at FROM alerts WHERE camera_id=:cid AND alert_type='restricted_zone' AND created_at BETWEEN :start AND :end ORDER BY created_at"),
        {'cid':cid,'start':datetime.fromtimestamp(start,timezone.utc),'end':datetime.fromtimestamp(end,timezone.utc)}).mappings().all()
report={'start':start,'end':end,'samples':samples,'frames':frames,'database_alerts':[dict(a) for a in alerts],
        'redis_alerts':redis_events,'websocket_alerts':ws_events}
(out/'report.json').write_text(json.dumps(report,indent=2,default=str))
print(json.dumps({'samples':len(samples),'inside_samples':sum(s['inside'] for s in samples),
 'transitions':sorted({s['transition'] for s in samples}), 'overlay_frames':sum(any(b['type']=='restricted_zone' for t in p['tracks'] for b in t.get('behaviors',[])) for p in frames),
 'database_alerts':len(alerts),'redis_alerts':len(redis_events),'websocket_alerts':len(ws_events)}))
