"""Read-only native camera health and observed processed-frame rate check."""
import argparse, json, os, sys, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
from app.core.config import settings
from app.core.security import create_access_token
from ai_engine.identity.qr_identity import load_student_mapping
from sqlalchemy import create_engine,text
import redis

parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);args=parser.parse_args()
engine=create_engine(settings.SYNC_DATABASE_URL)
with engine.connect() as c:
    cameras=c.execute(text('SELECT id,name,status FROM cameras WHERE is_active=true')).mappings().all()
    user=c.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar()
r=redis.Redis.from_url(settings.REDIS_URL,socket_timeout=3)
seen={str(c['id']):set() for c in cameras};latest={};start=time.monotonic()
while time.monotonic()-start<10:
    for c in cameras:
        cid=str(c['id']);raw=r.get(f'camera:{cid}:tracks')
        if raw:
            payload=json.loads(raw);latest[cid]=payload
            seen[cid].add((payload.get('stream_session'),payload.get('frame_number')))
    time.sleep(.1)
duration=time.monotonic()-start
mapping=load_student_mapping(ROOT/settings.STUDENT_QR_WORKBOOK)
with urllib.request.urlopen('http://localhost:8000/health',timeout=5) as response:health=response.status
request=urllib.request.Request('http://localhost:8000/api/v1/streams/status',headers={'Authorization':'Bearer '+create_access_token(str(user))})
with urllib.request.urlopen(request,timeout=5) as response:stream_status=json.load(response)
report={'label':args.label,'health':health,'students':len(mapping),
        'profile_references':sum(bool(v.get('face_file')) for v in mapping.values()),
        'activity_debug':settings.ACTIVITY_DEBUG,'track_grace_secs':settings.QR_TRACK_GRACE_SECS,
        'stream_status':stream_status,
        'cameras':[{'name':c['name'],'status':c['status'],
                    'observed_processed_fps':round(max(0,len(seen[str(c['id'])])-1)/duration,2),
                    'current_person_tracks':sum(t.get('class_name')=='person' and t.get('time_since_update',0)==0
                                              for t in latest.get(str(c['id']),{}).get('tracks',[])),
                    'known_tracks':sum(bool(t.get('identity')) for t in latest.get(str(c['id']),{}).get('tracks',[]))}
                   for c in cameras]}
out=ROOT/'logs'/f'qr-identity-{args.label}.json';out.write_text(json.dumps(report,indent=2))
print(json.dumps(report))
