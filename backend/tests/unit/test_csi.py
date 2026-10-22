"""Canonical safety index regression tests; no live database changes."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services.safety_index import (
    calculate_campus_safety_index, score_to_level, get_campus_safety_index,
    get_safety_index_sync, publish_campus_safety_index, publish_safety_index_sync,
)

NOW = datetime(2026, 10, 2, 8, tzinfo=timezone.utc)


def event(severity="high", status="open", hours=0, kind="unauthorized_access"):
    return {"severity": severity, "status": status, "created_at": NOW - timedelta(hours=hours), "incident_type": kind}


def test_no_incidents():
    result = calculate_campus_safety_index([], NOW)
    assert result["overall_score"] == 100
    assert result["risk_level"] == "safe"
    assert result["anomaly_score"] == 100
    assert result["anomaly_count"] == 0


@pytest.mark.parametrize("severity,score", [("low",98),("medium",95),("high",90),("critical",80),("HIGH",90)])
def test_severity_penalties(severity, score):
    assert calculate_campus_safety_index([event(severity)], NOW)["overall_score"] == score


def test_resolved_reduced_impact():
    assert calculate_campus_safety_index([event("critical", "resolved")], NOW)["overall_score"] == 95
    assert calculate_campus_safety_index([event("critical", "acknowledged")], NOW)["overall_score"] == 80


@pytest.mark.parametrize("hours", [24, 25, 240])
def test_old_incidents_do_not_affect_score(hours):
    assert calculate_campus_safety_index([event(hours=hours)], NOW)["overall_score"] == 100


def test_time_decay():
    assert calculate_campus_safety_index([event("critical", hours=12)], NOW)["overall_score"] == 90


def test_score_bounds_and_future_timestamp():
    assert calculate_campus_safety_index([event("critical")] * 50, NOW)["overall_score"] == 0
    assert calculate_campus_safety_index([event("high", hours=-12)], NOW)["overall_score"] == 90
    assert calculate_campus_safety_index([], NOW)["overall_score"] <= 100


@pytest.mark.parametrize("score,level", [(100,"safe"),(90,"safe"),(89,"low_risk"),(75,"low_risk"),(74,"moderate"),(60,"moderate"),(59,"high_risk"),(40,"high_risk"),(39,"critical"),(0,"critical")])
def test_risk_levels(score, level):
    assert score_to_level(score) == level


def test_components_are_safety_scores_and_counts_are_separate():
    result = calculate_campus_safety_index([event(kind="anomaly")], NOW)
    assert result["anomaly_count"] == 1
    assert result["anomaly_score"] == 90
    assert result["crowd_score"] == 100
    assert result["active_alerts"] == 1


def test_database_models_and_naive_dates():
    row = SimpleNamespace(**event())
    row.created_at = NOW.replace(tzinfo=None)
    assert calculate_campus_safety_index([row], NOW)["overall_score"] == 90


@pytest.mark.asyncio
async def test_async_database_loader_combines_alerts_and_incidents(monkeypatch):
    import app.services.safety_index as module
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    monkeypatch.setattr(module, "datetime", Clock)
    db = AsyncMock()
    results = []
    for rows in ([event("high")], [event("critical")]):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        results.append(result)
    db.execute.side_effect = results
    data = await get_campus_safety_index(db)
    assert data["recent_events"] == 2
    assert db.execute.await_count == 2
    assert 70 <= data["overall_score"] <= 100


def test_sync_database_loader_uses_same_calculation():
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    assert get_safety_index_sync(session)["overall_score"] == 100
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_publication_contains_full_snapshot(monkeypatch):
    import json
    import app.db.redis_client as client
    redis = AsyncMock()
    monkeypatch.setattr(client, "get_redis", AsyncMock(return_value=redis))
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    data = await publish_campus_safety_index(db)
    channel, raw = redis.publish.call_args.args
    msg = json.loads(raw)
    assert channel == "csi_updates"
    assert msg["type"] == "csi_update"
    assert msg["overall_score"] == data["overall_score"] == 100
    assert msg["anomaly_score"] == 100
    assert msg["updated_at"] == data["updated_at"]


@pytest.mark.asyncio
async def test_publication_failure_does_not_undo_mutation(monkeypatch):
    import app.db.redis_client as client
    monkeypatch.setattr(client, "get_redis", AsyncMock(side_effect=RuntimeError("Redis unavailable")))
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    assert await publish_campus_safety_index(db) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("module_name,operation", [
    ("incidents", "create"), ("incidents", "resolve"), ("incidents", "update"), ("incidents", "delete"),
    ("alerts", "update"), ("alerts", "delete"),
])
async def test_mutations_publish_after_commit(monkeypatch, module_name, operation):
    import importlib
    import uuid
    module = importlib.import_module(f"app.api.v1.endpoints.{module_name}")
    calls = []
    db = AsyncMock()
    db.add = MagicMock()
    db.commit.side_effect = lambda: calls.append("commit")
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(id=uuid.uuid4())
    db.execute.return_value = result
    async def publish(db):
        calls.append("publish")
    monkeypatch.setattr(module, "publish_campus_safety_index", publish)
    user = SimpleNamespace(id=uuid.uuid4())
    record_id = uuid.uuid4()
    if operation == "create":
        await module.create_incident(module.IncidentCreate(title="Test", incident_type="other", severity="high"), db, user)
    elif operation == "resolve":
        await module.resolve_incident(record_id, db, user)
    elif operation == "update" and module_name == "incidents":
        await module.update_incident(record_id, module.IncidentUpdate(severity="critical", status="resolved"), db, user)
    elif operation == "update":
        await module.update_alert(record_id, module.AlertUpdate(severity="critical", status="resolved"), db, user)
    elif module_name == "incidents":
        await module.delete_incident(record_id, db, user)
    else:
        await module.delete_alert(record_id, db, user)
    assert calls == ["commit", "publish"]


@pytest.mark.asyncio
async def test_events_endpoint_shares_broadcast_manager():
    from app.api.v1.endpoints.websocket import manager
    from app.services.websocket_manager import ws_manager
    assert manager is ws_manager
    first, second = AsyncMock(), AsyncMock()
    await manager.connect(first, "same-user:tab1")
    await manager.connect(second, "same-user:tab2")
    try:
        await manager.broadcast({"type":"csi_update", "overall_score":90})
        first.send_text.assert_awaited_once()
        second.send_text.assert_awaited_once()
    finally:
        manager.disconnect("same-user:tab1")
        manager.disconnect("same-user:tab2")


def test_authenticated_events_socket_receives_csi():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.endpoints.websocket import router
    from app.services.websocket_manager import ws_manager
    from app.core.security import create_access_token
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/ws")
    with TestClient(app) as client:
        token = create_access_token("csi-test-user")
        with client.websocket_connect(f"/api/v1/ws/events?token={token}") as socket:
            client.portal.call(ws_manager.broadcast, {"type": "csi_update", "overall_score": 90, "risk_level": "safe"})
            message = socket.receive_json()
            assert message["overall_score"] == 90
            socket.send_text("ping")
            assert socket.receive_text() == "pong"


def test_campus_api_returns_canonical_data_and_database_failure_is_503():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.endpoints.csi import router
    from app.api.v1.endpoints.auth import get_current_user
    from app.db.database import get_db
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/csi")
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = result
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="test")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        response = client.get("/api/v1/csi/campus")
        assert response.status_code == 200
        assert response.json()["overall_score"] == 100
        db.execute.side_effect = RuntimeError("Database unavailable")
        response = client.get("/api/v1/csi/campus")
        assert response.status_code == 503
        assert "overall_score" not in response.json()


def test_incident_api_creation_and_resolution_change_canonical_csi(monkeypatch):
    """Exercise actual HTTP routes/formula with isolated records, without live DB edits."""
    import json
    import uuid
    from datetime import datetime, timezone
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.endpoints import csi, incidents
    from app.api.v1.endpoints.auth import get_current_user
    from app.db.database import get_db
    from app.models.incident import Incident
    import app.db.redis_client as redis_client

    class IsolatedSession:
        def __init__(self):
            self.rows = []

        def add(self, row):
            row.id = uuid.uuid4()
            row.created_at = datetime.now(timezone.utc)
            row.status = "open"
            self.rows.append(row)

        async def commit(self):
            pass

        async def refresh(self, row):
            pass

        async def execute(self, query):
            result = MagicMock()
            rows = self.rows if query.column_descriptions[0]["entity"] is Incident else []
            result.scalars.return_value.all.return_value = rows
            result.scalar_one_or_none.return_value = rows[0] if rows else None
            return result

    db = IsolatedSession()
    redis = AsyncMock()
    monkeypatch.setattr(redis_client, "get_redis", AsyncMock(return_value=redis))
    app = FastAPI()
    app.include_router(csi.router, prefix="/api/v1/csi")
    app.include_router(incidents.router, prefix="/api/v1/incidents")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    with TestClient(app) as client:
        assert client.get("/api/v1/csi/campus").json()["overall_score"] == 100
        response = client.post("/api/v1/incidents/", json={"title":"Isolated test", "incident_type":"other", "severity":"high"})
        assert response.status_code == 201
        assert client.get("/api/v1/csi/campus").json()["overall_score"] == 90
        assert json.loads(redis.publish.call_args.args[1])["overall_score"] == 90
        response = client.patch(f"/api/v1/incidents/{response.json()['id']}/resolve")
        assert response.status_code == 200
        assert client.get("/api/v1/csi/campus").json()["overall_score"] == 98
        assert json.loads(redis.publish.call_args.args[1])["overall_score"] == 98
