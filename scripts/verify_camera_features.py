"""Reversible authenticated API smoke test; never enables test geometry."""
import json,os,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
from app.core.config import settings
from app.core.security import create_access_token
from sqlalchemy import create_engine,text
engine=create_engine(settings.SYNC_DATABASE_URL)
with engine.connect() as c:user=c.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar()
headers={'Authorization':'Bearer '+create_access_token(str(user)),'Content-Type':'application/json'}
def call(path,method='GET',data=None):
    request=urllib.request.Request('http://localhost:8000/api/v1/'+path,method=method,headers=headers,
        data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(request,timeout=10) as response:
        raw=response.read()
        return json.loads(raw) if raw else None
report=[]
for camera in call('cameras/'):
    cid=camera['id'];base='cameras/'+cid;zone_id=None;line_created=False
    before=call(base+'/zones');old_line=call(base+'/counting-line')
    result={'camera':camera['name'],'initial_status':camera['status']}
    try:
        data={'name':'Temporary disabled API verification','zone_points':[{'x':.1,'y':.1},{'x':.3,'y':.1},{'x':.3,'y':.3}],
              'alert_level':'high','is_active':False}
        created=call(base+'/zones','POST',data);zone_id=created['id']
        assert created['zone_points']==data['zone_points'] and not created['is_active']
        data['name']='Temporary edited disabled verification'
        edited=call(base+'/zones/'+zone_id,'PUT',data)
        assert edited['name']==data['name'] and not edited['is_active']
        call(base+'/zones/'+zone_id,'DELETE');zone_id=None
        assert {z['id'] for z in call(base+'/zones')}=={z['id'] for z in before}
        result['zone_create_edit_clear']='passed'
        if old_line is None:
            line={'points':[{'x':.1,'y':.5},{'x':.9,'y':.5}],'enabled':False}
            line_created=True;call(base+'/counting-line','PUT',line)
            assert call(base+'/counting-line')==line
            call(base+'/counting-line','DELETE');line_created=False
            assert call(base+'/counting-line') is None
            result['line_save_clear']='passed'
        else:result['line_save_clear']='existing line preserved; write test skipped'
    finally:
        if zone_id:call(base+'/zones/'+zone_id,'DELETE')
        if line_created:call(base+'/counting-line','DELETE')
    report.append(result)
status=call('streams/status')
output={'geometry_api':report,'streams':status}
(ROOT/'logs/camera-features-api-verification.json').write_text(json.dumps(output,indent=2))
print(json.dumps(output))
