"""Record labeled live activity and real alert delivery; never inject detections."""
import os,sys,json,time,asyncio,argparse
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
from sqlalchemy import create_engine,text
from app.core.config import settings
from app.core.security import create_access_token
import websockets
parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);parser.add_argument('--seconds',type=float,default=25)
args=parser.parse_args();log=ROOT/'logs/backend.log';start=time.time();offset=log.stat().st_size
engine=create_engine(settings.SYNC_DATABASE_URL)
with engine.connect() as connection:user=connection.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar()
async def capture():
    events=[];deadline=time.monotonic()+args.seconds
    try:
        async with websockets.connect('ws://localhost:8000/api/v1/ws/events?token='+create_access_token(str(user)),open_timeout=5) as socket:
            last_ping=time.monotonic()
            while time.monotonic()<deadline:
                try:
                    if time.monotonic()-last_ping>=10:
                        await socket.send('ping');last_ping=time.monotonic()
                    raw=await asyncio.wait_for(socket.recv(),timeout=min(2,max(.1,deadline-time.monotonic())))
                    if raw=='pong':continue
                    event=json.loads(raw)
                    if event.get('type')=='new_alert':events.append(event)
                except asyncio.TimeoutError:continue
    except Exception as error:
        print('WebSocket validation:',type(error).__name__,flush=True)
        await asyncio.sleep(max(0,deadline-time.monotonic()))
    return events
print('Live action capture started: '+args.label,flush=True)
ws_events=asyncio.run(capture());end=time.time();samples=[];decoder=json.JSONDecoder()
with log.open('rb') as source:source.seek(offset);data=source.read().decode('utf-8',errors='replace')
for line in data.splitlines():
    if 'ACTIVITY_SAMPLE {' not in line:continue
    sample,_=decoder.raw_decode(line.split('ACTIVITY_SAMPLE ',1)[1])
    if start<=sample['sample_time']<=end and sample['camera_name']=='General Entrance':samples.append(sample)
with engine.connect() as connection:
    rows=connection.execute(text('SELECT id,alert_type,severity,title,created_at FROM alerts WHERE created_at>=:start ORDER BY created_at'),{'start':datetime.fromtimestamp(start,tz=timezone.utc)}).mappings().all()
report={'label':args.label,'start':start,'end':end,'samples':samples,'websocket_alerts':ws_events,'database_alerts':[{**row,'id':str(row['id']),'created_at':row['created_at'].isoformat()} for row in rows]}
(ROOT/f'logs/live-validation-{args.label}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'label':args.label,'samples':len(samples),'sleep_confirmed':sum(s['sleeping'].get('is_sleeping',False) for s in samples),
    'talk_confirmed':sum(s['talking'].get('is_talking',False) for s in samples),'phone_confirmed':sum(s['phone_use']['confirmed'] for s in samples),
    'eating_confirmed':sum(s['eating']['confirmed'] for s in samples),'database_alerts':report['database_alerts'],'websocket_alerts':len(ws_events)}))
