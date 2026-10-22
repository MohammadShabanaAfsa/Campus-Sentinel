import uuid
import asyncio
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.database import get_db
from app.models.camera import Camera, RestrictedZone
from app.schemas.camera import CameraCreate, CameraUpdate, CameraResponse, CameraSourceTest, RestrictedZoneCreate, RestrictedZoneResponse, CountingLine, CampusEventConfiguration
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User

router = APIRouter()


@router.post("/test-source")
async def test_source(data: CameraSourceTest, _: User = Depends(get_current_user)):
    if data.rtsp_url.isdigit():
        raise HTTPException(status_code=422, detail="Local webcam is managed by its active stream. Test a network source here.")
    from app.services.camera_probe import test_camera_source
    return await asyncio.to_thread(test_camera_source, data.rtsp_url)


@router.get("/", response_model=List[CameraResponse])
async def list_cameras(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Camera).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    camera_data: CameraCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    camera = Camera(**camera_data.model_dump())
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    # Kick off stream connection in background
    background_tasks.add_task(_connect_camera_stream, str(camera.id))
    return camera


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: uuid.UUID,
    camera_data: CameraUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    update_data = camera_data.model_dump(exclude_unset=True)
    source_changed = "rtsp_url" in update_data and update_data["rtsp_url"] != camera.rtsp_url
    if source_changed:
        if update_data["rtsp_url"] is None:
            raise HTTPException(status_code=422, detail="Camera source cannot be empty")
        # Probe only network sources, never re-open an occupied entrance webcam.
        if update_data["rtsp_url"].startswith(("http://", "https://", "rtsp://")):
            from app.services.camera_probe import test_camera_source
            result = await asyncio.to_thread(test_camera_source, update_data["rtsp_url"])
            if not result["frame_read"]:
                raise HTTPException(status_code=422, detail=result["message"])
        camera.stream_url = update_data["rtsp_url"]
        camera.config = {**(camera.config or {}), "last_error": None}
    for k, v in update_data.items():
        setattr(camera, k, v)
    await db.commit()
    await db.refresh(camera)
    if source_changed or {"is_active", "zone_type"}.intersection(update_data):
        background_tasks.add_task(_refresh_camera_stream, str(camera.id), camera.is_active)
    return camera


def _refresh_camera_stream(camera_id: str, is_active: bool):
    from ai_engine.vision.stream_manager import StreamManager
    manager = StreamManager.get_instance(camera_id)
    if is_active:
        manager.restart()
    else:
        manager.stop()


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    await db.delete(camera)
    await db.commit()


@router.post("/{camera_id}/zones", response_model=RestrictedZoneResponse, status_code=201)
async def create_restricted_zone(
    camera_id: uuid.UUID,
    zone_data: RestrictedZoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if await db.get(Camera,camera_id) is None:raise HTTPException(404,'Camera not found')
    zone = RestrictedZone(
        camera_id=camera_id,
        created_by=current_user.id,
        **zone_data.model_dump()
    )
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    return zone


@router.get("/{camera_id}/zones", response_model=List[RestrictedZoneResponse])
async def list_zones(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(
        select(RestrictedZone).where(RestrictedZone.camera_id == camera_id)
    )
    return result.scalars().all()


@router.put('/{camera_id}/zones/{zone_id}',response_model=RestrictedZoneResponse)
async def edit_zone(camera_id:uuid.UUID,zone_id:uuid.UUID,data:RestrictedZoneCreate,
                    db:AsyncSession=Depends(get_db),_:User=Depends(get_current_user)):
    zone=await db.get(RestrictedZone,zone_id)
    if zone is None or zone.camera_id!=camera_id:raise HTTPException(404,'Zone not found')
    for key,value in data.model_dump().items():setattr(zone,key,value)
    await db.commit();await db.refresh(zone)
    return zone


@router.delete('/{camera_id}/zones/{zone_id}',status_code=204)
async def clear_zone(camera_id:uuid.UUID,zone_id:uuid.UUID,db:AsyncSession=Depends(get_db),_:User=Depends(get_current_user)):
    zone=await db.get(RestrictedZone,zone_id)
    if zone is None or zone.camera_id!=camera_id:raise HTTPException(404,'Zone not found')
    await db.delete(zone)
    await db.commit()


@router.get('/{camera_id}/counting-line')
async def get_counting_line(camera_id:uuid.UUID,db:AsyncSession=Depends(get_db),_:User=Depends(get_current_user)):
    camera=await db.get(Camera,camera_id)
    if camera is None:raise HTTPException(404,'Camera not found')
    return (camera.config or {}).get('vehicle_counting_line')


@router.put('/{camera_id}/counting-line')
async def save_counting_line(camera_id:uuid.UUID,data:CountingLine,db:AsyncSession=Depends(get_db),_:User=Depends(get_current_user)):
    camera=await db.get(Camera,camera_id)
    if camera is None:raise HTTPException(404,'Camera not found')
    camera.config={**(camera.config or {}),'vehicle_counting_line':data.model_dump()}
    await db.commit()
    return data


@router.delete('/{camera_id}/counting-line',status_code=204)
async def clear_counting_line(camera_id:uuid.UUID,db:AsyncSession=Depends(get_db),_:User=Depends(get_current_user)):
    camera=await db.get(Camera,camera_id)
    if camera is None:raise HTTPException(404,'Camera not found')
    camera.config={key:value for key,value in (camera.config or {}).items() if key!='vehicle_counting_line'}
    await db.commit()


@router.get('/{camera_id}/campus-events',response_model=CampusEventConfiguration)
async def get_campus_events(camera_id:uuid.UUID,db:AsyncSession=Depends(get_db),_:User=Depends(get_current_user)):
    camera=await db.get(Camera,camera_id)
    if camera is None:raise HTTPException(404,'Camera not found')
    return (camera.config or {}).get('campus_events',{})


@router.put('/{camera_id}/campus-events',response_model=CampusEventConfiguration)
async def save_campus_events(camera_id:uuid.UUID,data:CampusEventConfiguration,db:AsyncSession=Depends(get_db),_:User=Depends(get_current_user)):
    camera=await db.get(Camera,camera_id)
    if camera is None:raise HTTPException(404,'Camera not found')
    camera.config={**(camera.config or {}),'campus_events':data.model_dump()}
    await db.commit()
    return data


async def _connect_camera_stream(camera_id: str):
    """
    Background task — starts the new camera's stream immediately via the
    already-running StreamManager (in-process daemon thread per camera_id),
    the same one app.main's lifespan starts at boot for every existing camera.
    """
    from ai_engine.vision.stream_manager import StreamManager
    StreamManager.get_instance(camera_id).start()
