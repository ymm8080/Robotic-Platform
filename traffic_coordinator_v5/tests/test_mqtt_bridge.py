"""Tests for MQTT → v5 core bridge."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from traffic_coordinator_v5.mqtt_bridge import _TOPIC_RE, _on_message


def test_topic_regex_matches_valid():
    m = _TOPIC_RE.match("vda5050/MiR/R-001/state")
    assert m is not None
    assert m.group(1) == "MiR"
    assert m.group(2) == "R-001"


def test_topic_regex_rejects_invalid():
    assert _TOPIC_RE.match("vda5050/MiR/R-001/order") is None
    assert _TOPIC_RE.match("other/MiR/R-001/state") is None
    assert _TOPIC_RE.match("vda5050/MiR/state") is None


def test_on_message_forwards_to_tc():
    """VDA5050 v4.1 state message is normalised and POSTed to TC."""
    raw_state = {
        "header": {"versionId": "4.1"},
        "robotId": "R-001",
        "batteryLevel": 75,
        "agvPosition": {"x": 1.0, "y": 2.0, "theta": 0.5},
    }
    msg = MagicMock()
    msg.topic = "vda5050/MiR/R-001/state"
    msg.payload = json.dumps(raw_state).encode()

    with patch("traffic_coordinator_v5.mqtt_bridge._post_ingest") as mock_post:
        _on_message(None, None, msg)
        mock_post.assert_called_once()
        brand, body = mock_post.call_args[0]
        assert brand == "MiR"
        # v4 field names should be translated to v5
        assert "robot_id" in body
        assert "robotId" not in body
        assert body["battery_percent"] == 75


def test_on_message_skips_non_state_topics():
    msg = MagicMock()
    msg.topic = "vda5050/MiR/R-001/order"
    msg.payload = b"{}"
    with patch("traffic_coordinator_v5.mqtt_bridge._post_ingest") as mock_post:
        _on_message(None, None, msg)
        mock_post.assert_not_called()


def test_on_message_handles_invalid_json():
    msg = MagicMock()
    msg.topic = "vda5050/MiR/R-001/state"
    msg.payload = b"not json"
    with patch("traffic_coordinator_v5.mqtt_bridge._post_ingest") as mock_post:
        _on_message(None, None, msg)
        mock_post.assert_not_called()


def test_on_message_defaults_version_to_4_1():
    raw_state = {"robotId": "R-001"}
    msg = MagicMock()
    msg.topic = "vda5050/GeekPlus/R-002/state"
    msg.payload = json.dumps(raw_state).encode()

    with patch("traffic_coordinator_v5.mqtt_bridge._post_ingest") as mock_post:
        _on_message(None, None, msg)
        mock_post.assert_called_once()
        brand, _body = mock_post.call_args[0]
        assert brand == "GeekPlus"
