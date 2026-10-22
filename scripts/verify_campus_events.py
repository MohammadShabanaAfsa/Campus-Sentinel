"""Reversible native API check; test schedules and exit polygons stay disabled."""
import os,sys,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
from app.core.config import settings
from app.core.security import create_access_token
from sqlalchemy import create_engine,text
engine=create_engine(settings.SYNC_DATABASE_URL)
with engine.connect() as c:user=c.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar()
headers={'Authorization':'Bearer '+create_access_token(str(user)),'Content-Type':'application/json'}
def call(path,method='GET',data=None):
    req=urllib.request.Request('http://localhost:8000/api/v1/'+path,headers=headers,method=method,data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
results=[]
for camera in call('cameras/'):
    path='cameras/'+camera['id']+'/campus-events';previous=call(path)
    record={'camera':camera['name'],'status':camera['status']}
    if previous['schedule']['enabled'] or previous['exit_zones'] or previous['schedule']['zones']:
        record['configuration_test']='existing configured rules preserved; mutation skipped'
    else:
        with engine.connect() as c:before=c.execute(text('SELECT config FROM cameras WHERE id=:id'),{'id':camera['id']}).scalar() or {}
        draft={**previous,'exit_zones':[{'id':'disabled-smoke-test','name':'Disabled API validation','enabled':False,
                                       'points':[{'x':.1,'y':.1},{'x':.3,'y':.1},{'x':.3,'y':.3}]}]}
        try:
            saved=call(path,'PUT',draft)
            assert saved==draft and call(path)==draft
            edited=json.loads(json.dumps(draft));edited['exit_zones'][0]['name']='Edited disabled exit'
            assert call(path,'PUT',edited)==edited
            record['configuration_test']='save/read/edit/clear passed'
        finally:call(path,'PUT',previous)
        assert call(path)==previous
        with engine.connect() as c:after=c.execute(text('SELECT config FROM cameras WHERE id=:id'),{'id':camera['id']}).scalar() or {}
        assert {k:v for k,v in before.items() if k!='campus_events'}=={k:v for k,v in after.items() if k!='campus_events'}
        record['other_camera_configuration']='preserved'
    results.append(record)
output={'configuration_api':results,'streams':call('streams/status')}
(ROOT/'logs/campus-events-native-verification.json').write_text(json.dumps(output,indent=2));print(json.dumps(output))
