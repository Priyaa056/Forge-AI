"""Platform accounts: registration, login, sessions and per-user project ownership."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.auth.security import create_access_token, decode_access_token, AuthError
from backend.services.project_store import ProjectStore

from .conftest import TASK_PROMPT


@pytest.fixture
def api(isolated_workspace):
    from backend.main import app

    with TestClient(app) as client:
        yield client


def register(api, email, password="correct-horse-1", **extra):
    return api.post("/api/auth/register", json={"email": email, "password": password, **extra})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_login_and_me(api):
    created = register(api, "Ada@Example.com", full_name="Ada Lovelace")
    assert created.status_code == 201
    body = created.json()
    assert body["token_type"] == "bearer" and body["expires_in"] > 0
    assert body["user"]["email"] == "ada@example.com" and body["user"]["full_name"] == "Ada Lovelace"
    assert "password_hash" not in body["user"]

    login = api.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct-horse-1"})
    assert login.status_code == 200
    me = api.get("/api/auth/me", headers=auth(login.json()["access_token"]))
    assert me.status_code == 200 and me.json()["email"] == "ada@example.com"


def test_registration_validation(api):
    assert register(api, "not-an-email").status_code == 422
    assert register(api, "short@example.com", password="1234567").status_code == 422
    assert register(api, "dup@example.com").status_code == 201
    duplicate = register(api, "DUP@example.com")
    assert duplicate.status_code == 409 and "already exists" in duplicate.json()["detail"]


def test_bad_credentials_and_tokens_are_rejected(api):
    register(api, "bob@example.com")
    assert api.post("/api/auth/login", json={"email": "bob@example.com", "password": "wrong-password"}).status_code == 401
    assert api.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever-1"}).status_code == 401
    assert api.get("/api/auth/me").status_code == 401
    assert api.get("/api/auth/me", headers=auth("abc.def.ghi")).status_code == 401
    assert api.get("/api/projects").status_code == 401
    assert api.post("/api/projects", json={"user_prompt": TASK_PROMPT}).status_code == 401


def test_passwords_are_hashed_at_rest(api, isolated_workspace):
    register(api, "carol@example.com", password="plain-text-secret-9")
    stored = (isolated_workspace / "users.json").read_text(encoding="utf-8")
    assert "plain-text-secret-9" not in stored and "pbkdf2_sha256$" in stored


def test_tampered_or_expired_tokens_fail(isolated_workspace, monkeypatch):
    token = create_access_token("usr_1", "a@b.co")
    header, payload, signature = token.split(".")
    with pytest.raises(AuthError):
        decode_access_token(f"{header}.{payload}x.{signature}")
    import backend.auth.security as security

    monkeypatch.setattr(security, "TOKEN_TTL_SECONDS", -10)
    with pytest.raises(AuthError, match="expired"):
        decode_access_token(security.create_access_token("usr_1", "a@b.co"))


def test_projects_are_private_to_their_owner(api, isolated_workspace):
    alice = register(api, "alice@example.com").json()["access_token"]
    bob = register(api, "bob@example.com").json()["access_token"]
    store = ProjectStore(isolated_workspace / "projects")
    alice_id = api.get("/api/auth/me", headers=auth(alice)).json()["id"]
    project = store.create_project(TASK_PROMPT, owner_id=alice_id)
    pid = project["project_id"]

    assert [p["project_id"] for p in api.get("/api/projects", headers=auth(alice)).json()["projects"]] == [pid]
    assert api.get("/api/projects", headers=auth(bob)).json()["projects"] == []
    for path in (f"/api/projects/{pid}", f"/api/projects/{pid}/preview", f"/api/projects/{pid}/events",
                 f"/api/projects/{pid}/runs/current/files"):
        assert api.get(path, headers=auth(bob)).status_code == 404, path
    assert api.post(f"/api/projects/{pid}/runs", json={"user_prompt": TASK_PROMPT}, headers=auth(bob)).status_code == 404
    detail = api.get(f"/api/projects/{pid}", headers=auth(alice)).json()
    assert "owner_id" not in detail and "preview_admin" not in detail


def test_first_account_adopts_projects_created_before_accounts(api, isolated_workspace):
    store = ProjectStore(isolated_workspace / "projects")
    legacy = store.create_project(TASK_PROMPT)  # no owner: created before accounts existed
    first = register(api, "first@example.com").json()["access_token"]
    second = register(api, "second@example.com").json()["access_token"]
    assert [p["project_id"] for p in api.get("/api/projects", headers=auth(first)).json()["projects"]] == [legacy["project_id"]]
    assert api.get("/api/projects", headers=auth(second)).json()["projects"] == []
    data = json.loads((isolated_workspace / "projects" / legacy["project_id"] / "project.json").read_text(encoding="utf-8"))
    assert data["owner_id"].startswith("usr_")
