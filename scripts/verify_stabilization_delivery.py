"""Controlled SYNTHETIC events through real DB/Redis/WebSocket; always cleaned up.

No camera actions or outbound notifications. Uses inactive fixture cameras only.
Writes received payloads for the real frontend handler/rendering regression test.
"""
import asyncio
import json
import os
import sys
import uuid
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
os.environ['DEBUG']='false'
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session
import redis
import websockets
from app.core.config import settings
from app.core.security import create_access_token
from app.models.camera import Camera
from app.models.alert import Alert
from app.services.tasks.alert_tasks import create_and_dispatch_alert,send_email_alert
from app.services.safety_index import publish_safety_index_sync
from app.services.vehicle_counts import VehicleCountStore
from app.core.celery_app import celery_app
from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions
from ai_engine.vision.behavior_overlay import PERSON_LABELS,CAMERA_LABELS,event

KINDS=list(PERSON_LABELS)+[k for k in CAMERA_LABELS if k not in ('crowd_formation','low_class_attention','missing_students','low_faculty_engagement')]

async def main():
    engine=create_engine(settings.SYNC_DATABASE_URL,pool_pre_ping=True)
    r=redis.Redis.from_url(settings.REDIS_URL,decode_responses=True)
    run_id=uuid.uuid4().hex;camera_ids=[uuid.uuid4(),uuid.uuid4()];received=[];stored_ids=[]
    pubsub=r.pubsub();pubsub.subscribe('alerts_channel')
    assert pubsub.get_message(timeout=3)['type']=='subscribe'
    report={'method':'SYNTHETIC controlled events over actual PostgreSQL/Redis/WebSocket','run_id':run_id}
    browser=playwright=None
    worker=None;worker_log=None;jobs=[]
    queue='validation-'+run_id
    try:
        worker_log=(ROOT/'logs/stabilization-validation-worker.log').open('w')
        worker=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker',queue],
            cwd=ROOT/'backend',stdout=worker_log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        for attempt in range(15):
            ready=celery_app.control.inspect(destination=[queue+'@stabilization'],timeout=1).ping()
            if ready:break
            if worker.poll() is not None:raise RuntimeError('Validation worker exited; inspect validation worker log')
            await asyncio.sleep(.25)
        else:raise RuntimeError('Validation worker did not become ready')
        def dispatch(cid,alert):
            job=create_and_dispatch_alert.apply_async(args=[str(cid),alert],queue=queue)
            jobs.append(job)
            job.get(timeout=30)
        with Session(engine) as db:
            user=db.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar_one()
            for cid in camera_ids:
                db.add(Camera(id=cid,name='Software validation '+run_id,location_name='Inactive software fixture',
                              rtsp_url='fixture://not-a-camera',is_active=False,status='offline'))
            db.commit()
        token=create_access_token(str(user))
        from playwright.async_api import async_playwright
        playwright=await async_playwright().start()
        browser=await playwright.chromium.launch(channel='msedge',headless=True)
        context=await browser.new_context()
        await context.add_cookies([{'name':'cs_token','value':token,'url':'http://localhost:3000'}])
        await context.add_init_script('''
            if(location.origin==='http://localhost:3000')localStorage.setItem('access_token',TOKEN);
            window.__validationEvents=[];window.__validationDeleted=[];
            const NativeWebSocket=window.WebSocket;
            window.WebSocket=class extends NativeWebSocket {
                constructor(...args){super(...args);this.addEventListener('message',event=>{
                    try{const msg=JSON.parse(event.data);
                        if(msg.type==='new_alert' && CAMERAS.includes(msg.alert.camera_id))window.__validationEvents.push(msg);
                        if(msg.type==='alert_deleted')window.__validationDeleted.push(msg.alert_id);
                    }catch(_){}
                });}
            };
        '''.replace('TOKEN',json.dumps(token)).replace('CAMERAS',json.dumps(list(map(str,camera_ids)))))
        page=await context.new_page()
        await page.goto('http://localhost:3000/dashboard',wait_until='networkidle')
        await page.get_by_text('Active Alerts',exact=True).wait_for()
        await page.wait_for_timeout(1500)
        async with websockets.connect('ws://localhost:8000/api/v1/ws/events?token='+token) as ws:
            await ws.send('ping')
            while await asyncio.wait_for(ws.recv(),10)!='pong':pass
            router=ConfirmedAlertTransitions();events=[]
            for kind in KINDS:
                metadata={'validation_run_id':run_id}
                if kind=='suspected_fight':metadata['track_ids']=[2,5]
                if kind=='abandoned_bag':metadata.update(bag_track_ids=[9],owner_track_ids=[2])
                if kind=='crowd_density':metadata['person_count']=5
                events.append(event(kind,'low' if kind in ('sleeping','talking','phone_use','eating') else 'medium' if kind=='loitering' else 'high',
                                    2 if kind in PERSON_LABELS else None,**metadata))
            alerts=router.update(events,[],now=0)
            with patch.object(send_email_alert,'delay',lambda payload:None):
                for alert in alerts:
                    dispatch(camera_ids[0],alert)
                    dispatch(camera_ids[0],alert)  # Same episode delivery retry.
                router.update([],[],now=5)
                renewed=router.update([event('phone_use','low',2,validation_run_id=run_id)],[],now=6)[0]
                dispatch(camera_ids[0],renewed)
                dispatch(camera_ids[1],alerts[0])  # Camera isolation.
            expected=len(KINDS)+2
            deadline=asyncio.get_running_loop().time()+15
            while len(received)<expected and asyncio.get_running_loop().time()<deadline:
                msg=json.loads(await asyncio.wait_for(ws.recv(),10))
                if msg.get('type')=='new_alert' and msg['alert'].get('camera_id') in map(str,camera_ids):received.append(msg)
            with Session(engine) as db:
                rows=db.execute(select(Alert).where(Alert.camera_id.in_(camera_ids))).scalars().all()
                stored_ids=[str(row.id) for row in rows]
                assert len(rows)==expected, f'Unexpected persisted alert count: {len(rows)}'
                assert len({msg['alert']['id'] for msg in received})==expected
                assert {row.extra_data['behavior_type'] for row in rows}==set(KINDS)
            published=[]
            while True:
                message=pubsub.get_message(ignore_subscribe_messages=True,timeout=.2)
                if not message:break
                msg=json.loads(message['data'])
                if msg.get('type')=='new_alert' and msg['alert'].get('camera_id') in map(str,camera_ids):published.append(msg)
            assert len(published)==expected
            await page.wait_for_function(f'window.__validationEvents.length==={expected}',timeout=15000)
            text_content=await page.locator('body').inner_text()
            for kind in KINDS:
                assert (PERSON_LABELS|CAMERA_LABELS)[kind] in text_content, f'Dashboard missing {kind}'
            report['browser_dashboard']={'method':'HEADLESS EDGE, actual served production dashboard',
                                          'received':expected,'all_15_labels_rendered':True}
            # Real PostgreSQL persistence/restart/date/isolation test on fixture cameras.
            from datetime import date,timedelta
            store=VehicleCountStore(engine,r);day=date.today()
            eid=uuid.uuid4().hex
            assert store.record(camera_ids[0],day,[(eid,'in'),(uuid.uuid4().hex,'out')])==(1,1)
            assert store.record(camera_ids[0],day,[(eid,'in')])==(1,1)
            assert VehicleCountStore(engine).load(camera_ids[0],day)==(1,1)
            assert store.load(camera_ids[0],day+timedelta(days=1))==(0,0)
            assert store.load(camera_ids[1],day)==(0,0)
            with patch.object(store,'_record_database',side_effect=RuntimeError('controlled database outage')):
                try:store.record(camera_ids[0],day,[(uuid.uuid4().hex,'in')])
                except RuntimeError:pass
            assert r.hlen(store._key(camera_ids[0]))==1
            assert VehicleCountStore(engine,r).load(camera_ids[0],day)==(2,1)
            assert r.hlen(store._key(camera_ids[0]))==0
            report['vehicle_outbox_recovery']='passed with actual Redis/PostgreSQL'
            report.update(types=KINDS,postgres_alerts=len(stored_ids),redis_messages=len(published),websocket_messages=len(received),
                          duplicate_episode_blocked=True,new_episode_allowed=True,camera_isolation=True,vehicle_postgresql='passed')
            report['celery_broker_delivery']='passed through isolated real Celery queue/worker; notifications disabled only in fixture worker'
            (ROOT/'logs/stabilization-dashboard-events.json').write_text(json.dumps(received,indent=2))
    finally:
        with Session(engine) as db:
            ids=db.execute(select(Alert.id).where(Alert.camera_id.in_(camera_ids))).scalars().all()
            stored_ids=list(map(str,ids))
            for cid in camera_ids:
                db.execute(text('DELETE FROM alerts WHERE camera_id=:cid'),{'cid':cid})
                db.execute(text('DELETE FROM cameras WHERE id=:cid'),{'cid':cid})
            db.commit()
            publish_safety_index_sync(db,r)
            assert not db.execute(select(Alert.id).where(Alert.camera_id.in_(camera_ids))).first()
        for alert_id in stored_ids:r.publish('alerts_channel',json.dumps({'type':'alert_deleted','alert_id':alert_id}))
        if browser is not None:
            try:
                await page.wait_for_function(f'window.__validationDeleted.length>={len(stored_ids)}',timeout=10000)
                report['browser_cleanup']='deletion events received by dashboard'
            finally:await browser.close()
        if playwright is not None:await playwright.stop()
        for cid in camera_ids:
            for pattern in (f'alert_episode:{cid}:*',f'alert_cooldown:{cid}:*',f'restricted_zone_episode:{cid}:*'):
                keys=list(r.scan_iter(match=pattern))
                if keys:r.delete(*keys)
            r.delete(f'vehicle_crossing_outbox:{cid}')
        report['fixture_cleanup']='passed'
        for job in jobs:job.forget()
        if worker is not None:
            import psutil
            try:
                process=psutil.Process(worker.pid)
                children=process.children(recursive=True)
                for child in children:child.terminate()
                process.terminate()
                psutil.wait_procs(children+[process],timeout=5)
            except psutil.NoSuchProcess:pass
        if worker_log is not None:worker_log.close()
        r.delete(queue)
        pubsub.close();r.close();engine.dispose()
        (ROOT/'logs/stabilization-delivery-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--worker':
        with patch.object(send_email_alert,'delay',lambda payload:None):
            celery_app.worker_main(['worker','--pool=solo','--loglevel=warning','-Q',sys.argv[2],
                '-n',sys.argv[2]+'@stabilization','--without-gossip','--without-mingle','--without-heartbeat'])
    else:asyncio.run(main())
