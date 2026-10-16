"""Tests for the donation goal endpoint (/api/donations/progress)."""

import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from titrack.api.app import create_app
from titrack.api.routes import donations
from titrack.db.connection import Database


@pytest.fixture
def client(tmp_path):
    db = Database(tmp_path / "test.db", auto_seed=False)
    db.connect()
    yield TestClient(create_app(db, collector_running=False))
    db.close()


@pytest.fixture(autouse=True)
def reset_cache():
    donations._cached = None
    yield
    donations._cached = None


class FakeUrlopen:
    """Stand-in for urllib.request.urlopen that records calls."""

    def __init__(self, body=None, error=None):
        self.body = body
        self.error = error
        self.calls = []

    def __call__(self, req, timeout=None):
        self.calls.append((req, timeout))
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.body).encode("utf-8"))


def test_progress_from_rpc(client, monkeypatch):
    fake = FakeUrlopen(body=[{"month_total": "37.50", "goal": 100, "currency": "USD", "month_start": "2026-10-01T00:00:00+00:00"}])
    monkeypatch.setattr(donations.urllib.request, "urlopen", fake)

    data = client.get("/api/donations/progress").json()

    assert data == {"available": True, "month_total": 37.5, "goal": 100.0, "currency": "USD"}
    req, timeout = fake.calls[0]
    assert req.full_url.endswith("/rest/v1/rpc/get_donation_progress")
    assert timeout == donations.REQUEST_TIMEOUT_SECONDS


def test_unavailable_when_offline(client, monkeypatch):
    fake = FakeUrlopen(error=urllib.error.URLError("offline"))
    monkeypatch.setattr(donations.urllib.request, "urlopen", fake)

    assert client.get("/api/donations/progress").json()["available"] is False


def test_unavailable_when_rpc_missing(client, monkeypatch):
    # Backend not migrated yet: PostgREST 404s the unknown function
    error = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    monkeypatch.setattr(donations.urllib.request, "urlopen", FakeUrlopen(error=error))

    assert client.get("/api/donations/progress").json()["available"] is False


def test_result_cached_between_requests(client, monkeypatch):
    fake = FakeUrlopen(body=[{"month_total": 5, "goal": 100, "currency": "USD"}])
    monkeypatch.setattr(donations.urllib.request, "urlopen", fake)

    client.get("/api/donations/progress")
    client.get("/api/donations/progress")

    assert len(fake.calls) == 1
