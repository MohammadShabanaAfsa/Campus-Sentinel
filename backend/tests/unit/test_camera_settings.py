import asyncio
import json
import subprocess
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import BackgroundTasks, HTTPException
from app.services import camera_probe
from app.api.v1.endpoints.cameras import update_camera
from app.schemas.camera import CameraUpdate
from ai_engine.vision.camera_manager import safe_source
from ai_engine.vision.stream_manager import StreamManager


def test_probe_timeout_is_bounded(monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs['timeout'] == 5
        raise subprocess.TimeoutExpired(args[0], 5)
    monkeypatch.setattr(camera_probe.subprocess, 'run', timeout)
    result = camera_probe.test_camera_source('http://phone:8080/video')
    assert not result['frame_read']
    assert result['message'] == 'Camera source unreachable: connection timed out'


def test_probe_success(monkeypatch):
    expected = dict(reachable=True, opened=True, frame_read=True, message='Camera stream is working')
    monkeypatch.setattr(camera_probe.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(expected)))
    assert camera_probe.test_camera_source('http://phone:8080/video') == expected


def test_source_logs_redact_credentials():
    assert safe_source('http://admin:secret@phone:8080/video?token=secret#secret') == 'http://phone:8080/video'


@pytest.mark.parametrize('working', [True, False])
def test_update_preserves_identity_and_location_and_restarts_only_target(monkeypatch, working):
    camera = SimpleNamespace(id=uuid.uuid4(), rtsp_url='http://old:8080/video', stream_url=None,
        latitude=17.3547, longitude=78.5936, location_name='Classroom', is_active=True,
        config={'zones': [1, 2]})
    entrance_manager = Mock()
    classroom_manager = Mock()
    lookup = Mock(side_effect=lambda camera_id: classroom_manager if camera_id == str(camera.id) else entrance_manager)
    monkeypatch.setattr(StreamManager, 'get_instance', lookup)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: camera)),
        commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(camera_probe, 'test_camera_source', lambda source: dict(frame_read=working, message='No frames received'))
    tasks = BackgroundTasks()
    coroutine = update_camera(camera.id, CameraUpdate(rtsp_url='http://new:8080/video'), tasks, db, None)
    if working:
        result = asyncio.run(coroutine)
        assert result is camera and camera.rtsp_url == camera.stream_url == 'http://new:8080/video'
        assert camera.config['zones'] == [1, 2]
        assert len(tasks.tasks) == 1
        assert tasks.tasks[0].args == (str(camera.id), True)
        db.commit.assert_awaited_once()
        asyncio.run(tasks())
        lookup.assert_called_once_with(str(camera.id))
        classroom_manager.restart.assert_called_once()
    else:
        with pytest.raises(HTTPException, match='No frames received'):
            asyncio.run(coroutine)
        assert camera.rtsp_url == 'http://old:8080/video'
        assert not tasks.tasks
        db.commit.assert_not_awaited()
    assert (camera.latitude, camera.longitude, camera.location_name) == (17.3547, 78.5936, 'Classroom')
    entrance_manager.restart.assert_not_called()
