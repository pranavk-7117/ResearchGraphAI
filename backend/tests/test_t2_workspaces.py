"""
T2 Workspace isolation tests.
Verifies that workspace CRUD works and that paper queries are isolated between workspaces.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db, SessionLocal
from app import models


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _cleanup_workspace(db: Session, workspace_id: int) -> None:
    ws = db.get(models.Workspace, workspace_id)
    if ws:
        db.delete(ws)
        db.commit()


# ---------------------------------------------------------------------------
# T2-a: POST /workspaces creates workspace with correct topic
# ---------------------------------------------------------------------------

def test_create_workspace_returns_correct_topic(client: TestClient):
    resp = client.post("/api/workspaces", json={"topic": "T2 Test Topic", "max_papers": 5})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["topic"] == "T2 Test Topic"
    assert body["id"] > 0
    assert body["paper_count"] == 0
    # Cleanup
    client.delete(f"/api/workspaces/{body['id']}")


# ---------------------------------------------------------------------------
# T2-b: GET /workspaces lists the created workspace
# ---------------------------------------------------------------------------

def test_list_workspaces_includes_created(client: TestClient):
    create_resp = client.post("/api/workspaces", json={"topic": "T2 List Test"})
    ws_id = create_resp.json()["id"]
    try:
        resp = client.get("/api/workspaces")
        assert resp.status_code == 200
        ids = [w["id"] for w in resp.json()]
        assert ws_id in ids
    finally:
        client.delete(f"/api/workspaces/{ws_id}")


# ---------------------------------------------------------------------------
# T2-c: Workspace isolation — paper from workspace A not visible in workspace B graph
# ---------------------------------------------------------------------------

def test_workspace_paper_isolation(client: TestClient, db: Session):
    ws_a = client.post("/api/workspaces", json={"topic": "Workspace A"}).json()
    ws_b = client.post("/api/workspaces", json={"topic": "Workspace B"}).json()
    ws_a_id = ws_a["id"]
    ws_b_id = ws_b["id"]

    try:
        # Direct DB insert of a paper into workspace A
        from app.services.embeddings import EmbeddingService, encode_embedding
        emb = encode_embedding(EmbeddingService().embed("test isolation paper"))
        paper_a = models.Paper(
            workspace_id=ws_a_id,
            title="Isolation Test Paper A",
            authors="Test Author",
            abstract="Unique abstract for workspace A isolation.",
            year=2024,
            source_type="test",
            whole_embedding=emb,
        )
        db.add(paper_a)
        db.commit()
        db.refresh(paper_a)

        # Papers endpoint scoped to workspace A should include it
        resp_a = client.get(f"/api/papers?workspace_id={ws_a_id}")
        titles_a = [p["title"] for p in resp_a.json()]
        assert "Isolation Test Paper A" in titles_a, f"Paper not in workspace A: {titles_a}"

        # Papers endpoint scoped to workspace B should NOT include it
        resp_b = client.get(f"/api/papers?workspace_id={ws_b_id}")
        titles_b = [p["title"] for p in resp_b.json()]
        assert "Isolation Test Paper A" not in titles_b, f"Paper leaked into workspace B: {titles_b}"

    finally:
        client.delete(f"/api/workspaces/{ws_a_id}")
        client.delete(f"/api/workspaces/{ws_b_id}")


# ---------------------------------------------------------------------------
# T2-d: DELETE /workspaces/{id} removes the workspace
# ---------------------------------------------------------------------------

def test_delete_workspace(client: TestClient):
    create_resp = client.post("/api/workspaces", json={"topic": "T2 Delete Test"})
    ws_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/workspaces/{ws_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    # Should be gone
    get_resp = client.get(f"/api/workspaces/{ws_id}")
    assert get_resp.status_code == 404
