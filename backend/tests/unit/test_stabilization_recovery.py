"""Recovery and camera-local transient-state reset without physical actions."""
import asyncio,json
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock
import pytest

@pytest.mark.asyncio
async def test_redis_subscription_recovers_without_duplicate_subscribers(monkeypatch):
 import app.main as main
 from app.services.websocket_manager import ws_manager
 subscriptions=[]
 class PubSub:
  def __init__(self,fail):self.fail=fail;self.closed=False
  async def subscribe(self,*channels):subscriptions.append(channels)
  async def listen(self):
   if self.fail:raise ConnectionError('temporary loss')
   yield {'type':'message','data':json.dumps({'type':'new_alert','alert':{'id':'fixture'}})}
   raise asyncio.CancelledError()
  async def aclose(self):self.closed=True
 first,second=PubSub(True),PubSub(False)
 monkeypatch.setattr(main,'get_redis',AsyncMock(side_effect=[SimpleNamespace(pubsub=lambda:first),SimpleNamespace(pubsub=lambda:second)]))
 monkeypatch.setattr(main.asyncio,'sleep',AsyncMock())
 broadcast=AsyncMock();monkeypatch.setattr(ws_manager,'broadcast',broadcast)
 with pytest.raises(asyncio.CancelledError):await main._redis_pubsub_listener()
 assert first.closed and second.closed and len(subscriptions)==2
 assert any(call.args[0].get('type')=='new_alert' for call in broadcast.await_args_list)
 assert sum(call.args[0].get('type')=='realtime_resync' for call in broadcast.await_args_list)==2

def test_classroom_restart_clears_only_local_transient_analytics():
 from ai_engine.classroom.classroom_monitor import ClassroomMonitor
 from ai_engine.classroom.attendance import AttendanceAnalyzer
 a=ClassroomMonitor.__new__(ClassroomMonitor)
 a._sleeping=Mock();a._talking=Mock();a._engagement=Mock()
 a._attendance=AttendanceAnalyzer('camera-A');other=AttendanceAnalyzer('camera-B')
 a._attendance._state.shortfall_since=1;other._state.shortfall_since=2
 a._low_attention_since=a._low_engagement_since=1
 a._low_attention_confirmed=a._low_engagement_confirmed=True
 a.reset_track_state()
 assert a._attendance._state.shortfall_since is None
 assert other._state.shortfall_since==2
 assert a._low_attention_since is None and not a._low_attention_confirmed
 assert a._low_engagement_since is None and not a._low_engagement_confirmed

def test_yolo_singleton_initialization_is_atomic_across_camera_threads(monkeypatch):
 from concurrent.futures import ThreadPoolExecutor
 import time
 from ai_engine.vision.detector import YOLODetector
 loaded=[]
 monkeypatch.setattr(YOLODetector,'_instances',{})
 def init(self,**kwargs):
  loaded.append(kwargs);time.sleep(.01)
 monkeypatch.setattr(YOLODetector,'__init__',init)
 with ThreadPoolExecutor(max_workers=8) as pool:
  instances=list(pool.map(lambda _:YOLODetector.get_instance(),range(8)))
 assert len(loaded)==1 and len({id(instance) for instance in instances})==1
