"""Verify native camera editing and PostgreSQL persistence without changing saved sources.

The database update runs inside an outer transaction that is always rolled back.
--runtime additionally checks the running API and restarts only Classroom.
"""
import argparse
import asyncio
import functools
import json
import os
import sys
import tempfile
import threading
import time
from datetime import timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / "backend")
sys.path.insert(0, str(ROOT / "backend"))
os.environ.pop("DEBUG", None)

import cv2
import httpx
import numpy as np
from fastapi import BackgroundTasks
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import settings
from app.core.security import create_access_token
from app.models.camera import Camera
from app.api.v1.endpoints.cameras import update_camera
from app.schemas.camera import CameraUpdate
from app.services.camera_probe import test_camera_source
from ai_engine.vision.camera_manager import safe_source


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


async def verify_database(source):
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
                    camera = (await db.execute(select(Camera).where(Camera.name == "Classroom"))).scalar_one()
                    before = (camera.id, camera.latitude, camera.longitude, camera.location_name, camera.zone_type, camera.config)
                    tasks = BackgroundTasks()
                    await update_camera(camera.id, CameraUpdate(rtsp_url=source), tasks, db, None)
                    await db.refresh(camera)
                    assert camera.rtsp_url == camera.stream_url == source
                    assert before[:5] == (camera.id, camera.latitude, camera.longitude, camera.location_name, camera.zone_type)
                    assert {k:v for k,v in (before[5] or {}).items() if k != 'last_error'} == {k:v for k,v in (camera.config or {}).items() if k != 'last_error'}
                    assert len(tasks.tasks) == 1 and tasks.tasks[0].args == (str(camera.id), True)
                    print("PostgreSQL update verified: same Classroom row, coordinates/config preserved, one targeted restart queued; rolling back test source.")
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def runtime():
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as connection:
            user = (await connection.execute(text("SELECT id FROM users WHERE is_active=true LIMIT 1"))).scalar_one()
    finally:
        await engine.dispose()
    token = create_access_token(str(user), expires_delta=timedelta(minutes=2))
    with httpx.Client(base_url="http://localhost:8000", headers={"Authorization":f"Bearer {token}"}, trust_env=False, timeout=12) as client:
        assert client.get('/health').json()['status'] == 'healthy'
        cameras = client.get('/api/v1/cameras/').json()
        classroom = next(c for c in cameras if c['name'] == 'Classroom')
        entrance = next(c for c in cameras if c['name'] == 'General Entrance')
        before = client.get('/api/v1/streams/status').json()[entrance['id']]
        started = time.monotonic()
        response = client.post('/api/v1/cameras/test-source', json={'rtsp_url':classroom['rtsp_url']})
        response.raise_for_status()
        print('Saved Classroom source:', safe_source(classroom['rtsp_url']))
        print('Native API probe:', response.json(), 'elapsed:', round(time.monotonic()-started,2))
        restart = client.post(f"/api/v1/streams/{classroom['id']}/restart")
        restart.raise_for_status()
        await asyncio.sleep(4)
        after = client.get('/api/v1/streams/status').json()
        entrance_after = after[entrance['id']]
        assert entrance_after['frames_processed'] >= before['frames_processed']
        assert entrance_after['uptime_secs'] >= before['uptime_secs']
        cameras_after = client.get('/api/v1/cameras/').json()
        saved = next(c for c in cameras_after if c['id']==classroom['id'])
        assert (saved['rtsp_url'],saved['latitude'],saved['longitude']) == (classroom['rtsp_url'],classroom['latitude'],classroom['longitude'])
        assert next(c for c in cameras_after if c['id']==entrance['id'])['status'] == 'online'
        print('Classroom runtime:', after[classroom['id']])
        print('Entrance runtime:', entrance_after)
        print('Entrance kept processing across Classroom restart; API remains healthy:',client.get('/health').status_code)
    with httpx.Client(trust_env=False, timeout=15) as client:
        page = client.get('http://localhost:3000/cameras', cookies={'cs_token':token})
        assert page.status_code == 200
        print('Production Cameras page:',page.status_code)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        video = Path(directory)/'test.avi'
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 10, (160,120))
        assert writer.isOpened()
        for _ in range(30):
            writer.write(np.full((120,160,3), 120, dtype=np.uint8))
        writer.release()
        server = ThreadingHTTPServer(('127.0.0.1',0), functools.partial(QuietHandler, directory=directory))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            source = f'http://127.0.0.1:{server.server_port}/test.avi'
            result = test_camera_source(source)
            assert result['frame_read'], result
            print('Native reachable HTTP/OpenCV frame test:', result)
            await verify_database(source)
        finally:
            server.shutdown(); server.server_close(); thread.join()
    if args.runtime:
        await runtime()


if __name__ == '__main__':
    asyncio.run(main())
