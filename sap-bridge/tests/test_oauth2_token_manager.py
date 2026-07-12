"""Tests for OAuth2TokenManager — SAP S/4HANA client_credentials flow."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from backends.ewm_backend import EwmBackend
from backends.oauth2_token_manager import OAuth2TokenManager


def _mock_redis():
    """Create a fakeredis-compatible mock with dict-backed storage."""
    store = {}
    r = MagicMock()
    r.get = lambda key: store.get(key)
    r.setex = lambda key, ttl, val: store.__setitem__(key, val)
    r.set = lambda key, val: store.__setitem__(key, val)
    r.delete = lambda key: store.pop(key, None)
    r.close = lambda: None
    return r, store


def test_oauth2_fetch_new_token():
    """fetch_new should POST to token_url and cache the access_token."""
    redis_mock, store = _mock_redis()
    mgr = OAuth2TokenManager(
        redis_client=redis_mock,
        token_url="https://sap:44300/token",
        client_id="test_client",
        client_secret="test_secret",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "abc123", "expires_in": 3600}
    with patch.object(httpx.Client, "post", return_value=mock_resp):
        token = mgr.fetch_new(httpx.Client())
    assert token == "abc123"
    assert "sap:oauth2:token:https://sap:44300/token" in store


def test_oauth2_get_token_from_cache():
    """get_token should return cached token without HTTP call."""
    redis_mock, store = _mock_redis()
    store["sap:oauth2:token:https://sap:44300/token"] = "cached_xyz"
    mgr = OAuth2TokenManager(
        redis_client=redis_mock,
        token_url="https://sap:44300/token",
        client_id="c",
        client_secret="s",
    )
    assert mgr.get_token() == "cached_xyz"


def test_oauth2_invalidate():
    """invalidate should remove the cached token."""
    redis_mock, store = _mock_redis()
    key = "sap:oauth2:token:https://sap:44300/token"
    store[key] = "old"
    mgr = OAuth2TokenManager(
        redis_client=redis_mock,
        token_url="https://sap:44300/token",
        client_id="c",
        client_secret="s",
    )
    assert mgr.get_token() == "old"
    mgr.invalidate()
    assert mgr.get_token() is None


def test_oauth2_fetch_failure_raises():
    """fetch_new should raise RuntimeError on non-200 response."""
    redis_mock, _ = _mock_redis()
    mgr = OAuth2TokenManager(
        redis_client=redis_mock,
        token_url="https://sap:44300/token",
        client_id="c",
        client_secret="s",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    with patch.object(httpx.Client, "post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="401"):
            mgr.fetch_new(httpx.Client())


def test_oauth2_missing_access_token_raises():
    """fetch_new should raise if response has no access_token."""
    redis_mock, _ = _mock_redis()
    mgr = OAuth2TokenManager(
        redis_client=redis_mock,
        token_url="https://sap:44300/token",
        client_id="c",
        client_secret="s",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"error": "invalid_client"}
    with patch.object(httpx.Client, "post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="missing access_token"):
            mgr.fetch_new(httpx.Client())


def test_oauth2_get_valid_token_uses_cache():
    """get_valid_token should return cached token without fetching."""
    redis_mock, store = _mock_redis()
    store["sap:oauth2:token:https://sap:44300/token"] = "cached"
    mgr = OAuth2TokenManager(
        redis_client=redis_mock,
        token_url="https://sap:44300/token",
        client_id="c",
        client_secret="s",
    )
    assert mgr.get_valid_token(httpx.Client()) == "cached"


def test_ewm_backend_oauth2_init_requires_token_url():
    with pytest.raises(ValueError, match="token_url"):
        EwmBackend(config={"auth_mode": "oauth2", "oauth2": {"client_id": "x"}})


def test_ewm_backend_oauth2_init_requires_client_id():
    with pytest.raises(ValueError, match="client_id"):
        EwmBackend(config={"auth_mode": "oauth2", "oauth2": {"token_url": "x"}})


def test_ewm_backend_basic_auth_backward_compatible():
    backend = EwmBackend(config={"user": "admin", "password": "secret"})
    assert backend._auth_mode == "basic"
    assert backend._auth == ("admin", "secret")
    assert backend._oauth2 is None


def test_ewm_backend_oauth2_validate_config():
    backend = EwmBackend(config={
        "auth_mode": "oauth2",
        "base_url": "http://sap:8000",
        "oauth2": {"token_url": "x", "client_id": "c", "client_secret": "s"},
    })
    auth_errors = [e for e in backend.validate_config() if "OAuth2" in e]
    assert auth_errors == []


def test_ewm_backend_oauth2_is_configured():
    backend = EwmBackend(config={
        "auth_mode": "oauth2",
        "oauth2": {"token_url": "x", "client_id": "c", "client_secret": "s"},
    })
    assert backend._is_configured() is True


def test_ewm_backend_get_auth_for_request_oauth2():
    backend = EwmBackend(config={
        "auth_mode": "oauth2",
        "oauth2": {"token_url": "x", "client_id": "c", "client_secret": "s"},
    })
    assert backend._get_auth_for_request() is None


def test_ewm_backend_get_auth_for_request_basic():
    backend = EwmBackend(config={"user": "admin", "password": "secret"})
    assert backend._get_auth_for_request() == ("admin", "secret")
