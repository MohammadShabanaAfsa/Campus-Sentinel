"""Native live-stream check and overlay rendering cost measurement.

--baseline records current live FPS before loading updated code.
No analyzer results are injected into the live cameras or Redis.
"""
import argparse
import asyncio
import base64
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / "backend")
sys.path.insert(0, str(ROOT / "backend"))
os.environ.pop("DEBUG", None)

import cv2
import httpx
import numpy as np
import websockets
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.core.security import create_access_token
from ai_engine.vision.frame_annotator import FrameAnnotator
from ai_engine.vision.behavior_overlay import BehaviorOverlayCache, event


def draw_benchmark():
    # Isolated benchmark inputs, never sent to a stream, analyzer, or database.
    frame = np.zeros((720,1280,3),np.uint8)
    normal = [dict(track_id=i,class_name="person",confidence=.84,bbox=[40+i*160,180,130+i*160,500]) for i in range(6)]
    annotated = [{**t,"behaviors":[{**event("running","medium",t["track_id"]),"detected_at":time.time()}]} for t in normal]
    renderer = FrameAnnotator()
    measurements = {}
    for name, tracks in (("normal",normal),("behavior",annotated)):
        timings=[]
        for _ in range(110):
            image=frame.copy()
            started=time.perf_counter()
            renderer.draw(image,tracks)
            timings.append((time.perf_counter()-started)*1000)
        measurements[name+"_median_ms"]=round(float(np.median(timings[10:])),3)
        measurements[name+"_p95_ms"]=round(float(np.percentile(timings[10:],95)),3)
    cache = BehaviorOverlayCache("benchmark")
    cache.update("behavior",dict(stream_session="benchmark",observed_at=time.time(),frame_number=30,
                                overlay_events=[event("running","medium",t["track_id"]) for t in normal]))
    started=time.perf_counter()
    for _ in range(1000): cache.attach(normal)
    measurements["cache_attach_ms"]=round((time.perf_counter()-started),3)  # /1000 calls *1000 ms
    measurements["extra_drawing_median_ms"]=round(measurements["behavior_median_ms"]-measurements["normal_median_ms"],3)
    return measurements


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',action='store_true')
    args=parser.parse_args()
    engine=create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.connect() as conn:
            user=conn.execute(text('SELECT id FROM users WHERE is_active=true LIMIT 1')).scalar_one()
    finally:
        engine.dispose()
    token=create_access_token(str(user),expires_delta=timedelta(minutes=2))
    headers={'Authorization':'Bearer '+token}
    report={}
    with httpx.Client(base_url='http://localhost:8000',headers=headers,trust_env=False,timeout=15) as client:
        cameras_response=client.get('/api/v1/cameras/'); cameras_response.raise_for_status()
        cameras=[c for c in cameras_response.json() if c['name'] in ('General Entrance','Classroom')]
        assert len(cameras)==2
        before=client.get('/api/v1/streams/status').json()
        started=time.monotonic()
        await asyncio.sleep(8)
        after=client.get('/api/v1/streams/status').json()
        elapsed=time.monotonic()-started
        for camera in cameras:
            cid=camera['id']; status=after[cid]
            item={'id':cid,'source':camera['rtsp_url'],'state':status['state'],
                  'fps':round((status['frames_processed']-before[cid]['frames_processed'])/elapsed,2),
                  'last_frame_age_secs':status['last_frame_age_secs'], 'last_error':status.get('last_error')}
            if not args.baseline:
                if status['state'] != 'running':
                    assert camera['name'] != 'General Entrance', status
                    item['verification']='Source unavailable; no live JPEG to verify'
                    report[camera['name']]=item
                    continue
                assert status['state']=='running' and status['last_frame_age_secs']<10,status
                payload=client.get(f'/api/v1/streams/{cid}/tracks').json()
                assert 'camera_behaviors' in payload and 'stream_session' in payload
                for track in payload['tracks']:
                    assert 'behaviors' in track
                    assert all(b['track_id']==track['track_id'] for b in track['behaviors'])
                    assert 'identity' in track
                    identity = track['identity']
                    if identity is not None:
                        assert identity['track_id']==track['track_id'] and identity['method']=='qr' and identity['verified'] is True
                assert all(b['track_id'] is None for b in payload['camera_behaviors'])
                async with websockets.connect(f'ws://localhost:8000/api/v1/ws/camera/{cid}/stream?token={token}',open_timeout=10) as socket:
                    message=json.loads(await asyncio.wait_for(socket.recv(),timeout=10))
                    assert message['type']=='frame'
                    image=cv2.imdecode(np.frombuffer(base64.b64decode(message['data']),np.uint8),cv2.IMREAD_COLOR)
                    assert image is not None
                    item['websocket_jpeg_shape']=list(image.shape)
                item['track_count']=len(payload['tracks'])
                item['qr_identity_count']=sum(t.get('identity') is not None for t in payload['tracks'])
                item['camera_behaviors']=payload['camera_behaviors']
            report[camera['name']]=item
        assert client.get('/health').json()['status']=='healthy'
    if not args.baseline:
        report['drawing_benchmark']=draw_benchmark()
        baseline=ROOT/'logs'/'behavior-overlay-baseline.json'
        if baseline.exists():
            report['baseline']=json.loads(baseline.read_text())
    destination=ROOT/'logs'/('behavior-overlay-baseline.json' if args.baseline else 'behavior-overlay-verification.json')
    destination.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    asyncio.run(main())
