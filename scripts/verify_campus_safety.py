"""Local smoke check: real CSI API -> Redis -> authenticated events WebSocket.

Uses an existing local account and database events. Creates no test incidents
or alerts. Run with backend/.venv/Scripts/python.exe scripts/verify_campus_safety.py.
"""
import asyncio
import json
import os
import sys
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / "backend")
sys.path.insert(0, str(ROOT / "backend"))
os.environ.pop("DEBUG", None)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import redis
import websockets
from app.core.config import settings
from app.core.security import create_access_token
from app.services.safety_index import publish_safety_index_sync


async def main():
    engine = create_engine(settings.SYNC_DATABASE_URL)
    client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        with engine.connect() as connection:
            user_id = connection.execute(text("SELECT id FROM users WHERE is_active=true LIMIT 1")).scalar_one()
            cameras = connection.execute(text("SELECT id, name, status FROM cameras WHERE is_active=true")).all()
        token = create_access_token(str(user_id), expires_delta=timedelta(minutes=2))
        request = urllib.request.Request(
            "http://localhost:8000/api/v1/cameras/",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            configured = json.load(response)
        assert isinstance(configured, list)
        assert {str(camera.id) for camera in cameras} <= {camera["id"] for camera in configured}
        print(f"Authenticated camera API: {len(configured)} configured cameras")
        print(f"Backend IP_CAMERA_URL: {settings.IP_CAMERA_URL}")
        request = urllib.request.Request(
            "http://localhost:8000/api/v1/csi/campus",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
        assert 0 <= data["overall_score"] <= 100
        print(f"Authenticated CSI API: {data['overall_score']} / {data['risk_level'].upper()}")

        headers = {"Authorization": f"Bearer {token}", "Cookie": f"cs_token={token}"}
        for path in ("/dashboard", "/api/v1/csi/campus"):
            request = urllib.request.Request(f"http://localhost:3000{path}", headers=headers)
            with urllib.request.urlopen(request, timeout=15) as response:
                assert response.status == 200
                if path.startswith("/api/"):
                    proxied = json.load(response)
                    assert 0 <= proxied["overall_score"] <= 100
                    assert "updated_at" in proxied
        print("Production frontend: authenticated dashboard and CSI API proxy verified")

        def publish():
            with Session(engine) as session:
                return publish_safety_index_sync(session, client)

        async with websockets.connect(
            f"ws://localhost:8000/api/v1/ws/events?token={token}", open_timeout=10
        ) as socket:
            await socket.send("ping")
            while await asyncio.wait_for(socket.recv(), timeout=10) != "pong":
                pass
            expected = await asyncio.to_thread(publish)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(socket.recv(), timeout=10)
                if raw == "pong":
                    continue
                message = json.loads(raw)
                if message.get("type") == "csi_update" and message.get("updated_at") == expected["updated_at"]:
                    assert message["overall_score"] == expected["overall_score"]
                    assert message["anomaly_score"] == expected["anomaly_score"]
                    print("Redis -> events WebSocket: full canonical CSI snapshot delivered")
                    break
            else:
                raise AssertionError("CSI broadcast was not delivered")

        for camera in cameras:
            heartbeat = client.get(f"camera:{camera.id}:heartbeat")
            frame = client.get(f"camera:{camera.id}:latest_frame")
            assert camera.status == "online", f"{camera.name} is {camera.status}"
            assert heartbeat and time.time() - float(heartbeat) < 15, f"{camera.name}: stale heartbeat"
            assert frame, f"{camera.name}: no current frame"
            print(f"Camera verified: {camera.name}, online, fresh frame")
    finally:
        client.close()
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
