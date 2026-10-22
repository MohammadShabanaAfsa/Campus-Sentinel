"""Daily crossing persistence using real SQL transactions and injected dates."""
from datetime import date,timedelta
from sqlalchemy import create_engine
from app.services.vehicle_counts import VehicleCountStore
from ai_engine.vision.vehicle_counter import VehicleCounter

LINE={'enabled':True,'points':[{'x':.1,'y':.5},{'x':.9,'y':.5}]}
def car(y,tid=1):return {'class_name':'car','track_id':tid,'bbox':[450,y-40,550,y+40]}
def fixture():
 engine=create_engine('sqlite://')
 with engine.begin() as c:
  c.exec_driver_sql('CREATE TABLE vehicle_daily_counts(camera_id TEXT,count_date DATE,in_count INTEGER,out_count INTEGER,total_count INTEGER,updated_at TIMESTAMP, PRIMARY KEY(camera_id,count_date))')
  c.exec_driver_sql('CREATE TABLE vehicle_crossings(event_id TEXT PRIMARY KEY,camera_id TEXT,count_date DATE,direction TEXT)')
 return VehicleCountStore(engine)
def counter(store,camera,clock):
 c=VehicleCounter(camera,store,lambda:clock[0]);c.configure(LINE);return c

def test_in_out_restore_daily_rollover_and_camera_isolation():
 store=fixture();clock=[date(2026,10,21)];c=counter(store,'A',clock)
 assert c.update([car(300)],(1000,1000))['total']==0
 assert c.update([car(700)],(1000,1000))['in']==1
 assert c.update([car(300)],(1000,1000))['out']==1
 restarted=counter(store,'A',clock)
 assert restarted.update([car(300)],(1000,1000))=={'in':1,'out':1,'total':2}
 assert restarted.update([car(300)],(1000,1000))['total']==2
 assert counter(store,'B',clock).update([car(700)],(1000,1000))['total']==0
 clock[0]+=timedelta(days=1)
 assert restarted.update([car(700)],(1000,1000))['total']==0
 assert store.load('A',clock[0]-timedelta(days=1))==(1,1)

def test_retry_same_crossing_is_idempotent():
 store=fixture();day=date(2026,10,21)
 assert store.record('A',day,[('crossing','in')])==(1,0)
 assert store.record('A',day,[('crossing','in')])==(1,0)
 assert store.record('B',day,[('other','out')])==(0,1)

def test_no_database_write_on_unchanged_frames(monkeypatch):
 store=fixture();calls=[];record=store.record
 monkeypatch.setattr(store,'record',lambda *args:(calls.append(args),record(*args))[1])
 c=counter(store,'A',[date(2026,10,21)])
 for _ in range(30):c.update([car(300)],(1000,1000))
 assert not calls
 c.update([car(700)],(1000,1000))
 for _ in range(30):c.update([car(700)],(1000,1000))
 assert len(calls)==1

def test_durable_outbox_recovers_after_database_failure_and_restart(monkeypatch):
 import json
 class Outbox:
  def __init__(self):self.data={}
  def hset(self,key,mapping):self.data.setdefault(key,{}).update(mapping)
  def hgetall(self,key):return dict(self.data.get(key,{}))
  def hdel(self,key,*ids):
   for eid in ids:self.data.get(key,{}).pop(eid,None)
 outbox=Outbox();store=fixture();store.outbox=outbox;day=date(2026,10,21)
 record=store._record_database
 monkeypatch.setattr(store,'_record_database',lambda *args:(_ for _ in ()).throw(RuntimeError('temporary database outage')))
 import pytest
 with pytest.raises(RuntimeError):store.record('A',day,[('recover-me','in')])
 recovered=VehicleCountStore(store.engine,outbox)
 assert recovered.load('A',day)==(1,0)
 assert recovered.load('A',day)==(1,0)
 assert not outbox.hgetall(store._key('A'))
 assert recovered.load('B',day)==(0,0)
