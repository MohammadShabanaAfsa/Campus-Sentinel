"""Capture real phone/eating samples, WebSocket events and stored alerts."""
import argparse,asyncio,base64,json,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
from app.core.config import settings
from app.core.security import create_access_token
from sqlalchemy import create_engine,text
import redis,websockets
parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);parser.add_argument('--seconds',type=float,default=30)
parser.add_argument('--save-frames',action='store_true')
args=parser.parse_args();log=ROOT/'logs/backend.log';offset=log.stat().st_size;start=time.time()
engine=create_engine(settings.SYNC_DATABASE_URL)
with engine.connect() as c:user=c.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar()
async def observe():
    events=[];deadline=time.monotonic()+args.seconds
    async def save_frames():
        r=redis.Redis.from_url(settings.REDIS_URL);out=ROOT/'logs/phone-eating-repair';out.mkdir(exist_ok=True);n=0
        while time.monotonic()<deadline:
            n+=1
            for name,cid in [('entrance','1a32cb23-0820-4385-9ab5-de8e472e2c04'),('classroom','6cf7815f-009b-48e6-bf71-a7548a5e75b0')]:
                frame=r.get(f'camera:{cid}:latest_frame');tracks=r.get(f'camera:{cid}:tracks')
                if frame:
                    stem=out/f'{args.label}-{name}-{n:02}'
                    stem.with_suffix('.jpg').write_bytes(base64.b64decode(frame))
                    if tracks:stem.with_suffix('.json').write_bytes(tracks)
            await asyncio.sleep(1)
    writer=asyncio.create_task(save_frames()) if args.save_frames else None
    async with websockets.connect('ws://localhost:8000/api/v1/ws/events?token='+create_access_token(str(user)),close_timeout=1) as socket:
        ping=time.monotonic()
        while time.monotonic()<deadline:
            if time.monotonic()-ping>=10:await socket.send('ping');ping=time.monotonic()
            try:
                raw=await asyncio.wait_for(socket.recv(),timeout=min(2,max(.1,deadline-time.monotonic())))
                if raw=='pong':continue
                event=json.loads(raw)
                if event.get('type')=='new_alert' and event['alert']['alert_type'] in ('phone_use','eating'):events.append(event)
            except asyncio.TimeoutError:pass
    if writer:await writer
    return events
print('Phone/eating capture started: '+args.label,flush=True)
events=asyncio.run(observe());end=time.time();samples=[];decoder=json.JSONDecoder()
with log.open('rb') as f:f.seek(offset);lines=f.read().decode('utf-8',errors='replace').splitlines()
for line in lines:
    if 'PHONE_EATING_SAMPLE {' in line:
        sample,_=decoder.raw_decode(line.split('PHONE_EATING_SAMPLE ',1)[1]);samples.append(sample)
with engine.connect() as c:
    rows=c.execute(text("SELECT id,alert_type,severity,title,created_at FROM alerts WHERE created_at>=:start AND created_at<=:end AND alert_type IN ('phone_use','eating') ORDER BY created_at"),
        {'start':datetime.fromtimestamp(start,timezone.utc),'end':datetime.fromtimestamp(end,timezone.utc)}).mappings().all()
report={'label':args.label,'start':start,'end':end,'samples':samples,'websocket_alerts':events,
    'database_alerts':[{**r,'id':str(r['id']),'created_at':r['created_at'].isoformat()} for r in rows]}
out=ROOT/'logs/phone-eating-repair';out.mkdir(exist_ok=True);(out/f'live-{args.label}.json').write_text(json.dumps(report,indent=2))
frame=redis.Redis.from_url(settings.REDIS_URL).get('camera:1a32cb23-0820-4385-9ab5-de8e472e2c04:latest_frame')
if frame:(out/f'live-{args.label}.jpg').write_bytes(base64.b64decode(frame))
print(json.dumps({'label':args.label,'samples':len(samples),'phone_confirmed':sum(s['phone']['confirmed'] for s in samples),
    'eating_confirmed':sum(s['eating']['confirmed'] for s in samples),'database_alerts':report['database_alerts'],'websocket_alerts':len(events)}))
