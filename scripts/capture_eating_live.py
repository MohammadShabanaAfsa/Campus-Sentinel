"""Read-only General Entrance eating observation; never inject detections."""
import argparse, asyncio, base64, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / 'backend')
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DEBUG'] = 'false'
from app.core.config import settings
from app.core.security import create_access_token
from sqlalchemy import create_engine, text
import redis, websockets

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=float, default=75)
args = parser.parse_args()
cid = '1a32cb23-0820-4385-9ab5-de8e472e2c04'
out = ROOT / 'logs/eating-live-test' / datetime.now().strftime('%Y%m%d-%H%M%S')
out.mkdir(parents=True, exist_ok=True)
log = ROOT / 'logs/backend.log'
offset = log.stat().st_size
start = time.time()
engine = create_engine(settings.SYNC_DATABASE_URL)
r = redis.Redis.from_url(settings.REDIS_URL)
with engine.connect() as c:
    user = c.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar()

async def observe():
    events, snapshots = [], []
    deadline = time.monotonic() + args.seconds
    async def frames():
        last = None
        while time.monotonic() < deadline:
            raw = r.get(f'camera:{cid}:tracks')
            if raw:
                payload = json.loads(raw)
                number = (payload.get('stream_session'), payload.get('frame_number'))
                if number != last:
                    last = number
                    snapshots.append({'observed_at': time.time(), 'payload': payload})
                    stem = out / f'frame-{len(snapshots):03}'
                    stem.with_suffix('.json').write_text(json.dumps(payload))
                    frame = r.get(f'camera:{cid}:latest_frame')
                    if frame:
                        stem.with_suffix('.jpg').write_bytes(base64.b64decode(frame))
            await asyncio.sleep(.5)
    writer = asyncio.create_task(frames())
    async with websockets.connect('ws://localhost:8000/api/v1/ws/events?token=' + create_access_token(str(user)), close_timeout=1) as socket:
        print('EATING recorder connected; output: ' + str(out), flush=True)
        ping = time.monotonic()
        while time.monotonic() < deadline:
            if time.monotonic() - ping >= 10:
                await socket.send('ping')
                ping = time.monotonic()
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=min(2, max(.1, deadline-time.monotonic())))
                if raw == 'pong':
                    continue
                item = json.loads(raw)
                alert = item.get('alert', {})
                if item.get('type') == 'new_alert' and alert.get('camera_id') == cid and alert.get('alert_type') == 'eating':
                    events.append(item)
            except asyncio.TimeoutError:
                pass
    await writer
    return events, snapshots

events, snapshots = asyncio.run(observe())
end = time.time()
samples = []
with log.open('rb') as f:
    f.seek(offset)
    lines = f.read().decode('utf-8', errors='replace').splitlines()
for line in lines:
    if 'EATING_SAMPLE {' in line and 'PHONE_EATING_SAMPLE' not in line:
        sample, _ = json.JSONDecoder().raw_decode(line.split('EATING_SAMPLE ', 1)[1])
        if sample['camera_id'] == cid:
            samples.append(sample)
with engine.connect() as c:
    rows = c.execute(text("SELECT id,alert_type,severity,created_at FROM alerts WHERE camera_id=:cid AND alert_type='eating' AND created_at BETWEEN :start AND :end ORDER BY created_at"),
        {'cid':cid, 'start':datetime.fromtimestamp(start,timezone.utc), 'end':datetime.fromtimestamp(end,timezone.utc)}).mappings().all()
alerts = [{**row, 'id':str(row['id']), 'created_at':row['created_at'].isoformat()} for row in rows]
confirmed = [s for s in snapshots if any(b.get('type') == 'eating' for t in s['payload'].get('tracks',[]) for b in t.get('behaviors',[]))]
report = {'start':start, 'end':end, 'samples':samples, 'websocket_alerts':events, 'database_alerts':alerts,
          'snapshot_count':len(snapshots), 'confirmed_snapshots':confirmed}
(out/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'output':str(out), 'samples':len(samples), 'max_cycles':max((s['completed_cycles'] for s in samples),default=0),
                  'phases':sorted({s['current_phase'] for s in samples}), 'confirmed_snapshots':len(confirmed), 'alerts':alerts, 'websocket_alerts':len(events)}),flush=True)
