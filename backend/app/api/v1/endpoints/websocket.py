import json
import asyncio
from loguru import logger
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.websocket_manager import ws_manager

router = APIRouter()
manager = ws_manager


@router.websocket("/events")
async def websocket_events(websocket: WebSocket, token: str = Query(...)):
    """Real-time event stream: alerts, CSI updates, detections."""
    from app.core.security import decode_token
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001)
        return

    import uuid
    client_id = f"{payload.get('sub', 'unknown')}:{uuid.uuid4()}"
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        manager.disconnect(client_id)


@router.websocket("/camera/{camera_id}/stream")
async def websocket_camera_stream(websocket: WebSocket, camera_id: str, token: str = Query(...)):
    """Streams JPEG frames as base64 for a specific camera."""
    from app.core.security import decode_token

    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001)
        return

    await websocket.accept()

    # Use synchronous Redis in a thread to avoid async Redis compatibility issues
    import redis as sync_redis
    from app.core.config import settings
    r = sync_redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    loop = asyncio.get_event_loop()

    try:
        while True:
            try:
                frame_data = await loop.run_in_executor(
                    None, r.get, f"camera:{camera_id}:latest_frame"
                )
            except Exception as e:
                logger.warning(f"Redis read error in camera stream {camera_id}: {e}")
                await asyncio.sleep(0.5)
                continue

            if frame_data:
                try:
                    await websocket.send_text(json.dumps({"type": "frame", "data": frame_data}))
                except (WebSocketDisconnect, Exception):
                    break

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Camera stream WebSocket error ({camera_id}): {e}")
    finally:
        try:
            r.close()
        except Exception:
            pass
