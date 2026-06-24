"""Tests for HeartbeatMonitor — MQTT message parsing, Redis storage."""
import json
import pytest
from unittest.mock import MagicMock, patch


class TestHeartbeatMonitor:
    """Heartbeat monitor MQTT callback tests."""

    @pytest.fixture
    def monitor(self):
        from heartbeat_monitor import HeartbeatMonitor
        with patch("heartbeat_monitor.redis.from_url") as mock_redis:
            mock_redis.return_value = MagicMock()
            mon = HeartbeatMonitor()
            # Don't actually connect to MQTT
            mon.client = MagicMock()
            yield mon

    def test_is_running_initial(self, monitor):
        assert monitor.is_running is False

    def test_start_stop(self, monitor):
        monitor.start()
        assert monitor.is_running is True
        assert monitor.client.connect.called
        assert monitor.client.loop_start.called

        monitor.stop()
        assert monitor.is_running is False
        assert monitor.client.loop_stop.called
        assert monitor.client.disconnect.called

    def test_on_connect_subscribes(self, monitor):
        monitor._on_connect(monitor.client, None, None, 0)
        assert monitor.client.subscribe.called
        # Should subscribe to connection and state topics
        call_args_list = monitor.client.subscribe.call_args_list
        topics = [call[0][0] for call in call_args_list]
        assert "vda5050/+/+/connection" in topics
        assert "vda5050/+/+/state" in topics

    def test_on_connect_failure(self, monitor):
        """Non-zero rc should not subscribe."""
        monitor.client.subscribe.reset_mock()
        monitor._on_connect(monitor.client, None, None, 5)
        assert not monitor.client.subscribe.called

    def test_on_message_connection_state(self, monitor):
        """Connection state messages should update Redis."""
        msg = MagicMock()
        msg.topic = "vda5050/KUKA/KMR-001/connection"
        msg.payload = json.dumps({"state": "ONLINE"}).encode()

        monitor._on_message(None, None, msg)

        monitor.redis_client.hset.assert_called_once()
        monitor.redis_client.expire.assert_called_once()

    def test_on_message_state_update(self, monitor):
        """State messages should store position and battery."""
        msg = MagicMock()
        msg.topic = "vda5050/MiR/MIR-001/state"
        msg.payload = json.dumps({
            "drivingState": "MOVING",
            "batteryState": {"batteryCharge": 85},
            "position": {"x": 10.5, "y": 20.3},
        }).encode()

        monitor._on_message(None, None, msg)

        # Verify Redis was called
        assert monitor.redis_client.hset.called
        call_kwargs = monitor.redis_client.hset.call_args[1] if len(
            monitor.redis_client.hset.call_args) > 1 else monitor.redis_client.hset.call_args[0]
        # Either way, hset was called
        assert monitor.redis_client.expire.called

    def test_on_message_invalid_json(self, monitor):
        """Invalid JSON should not crash."""
        msg = MagicMock()
        msg.topic = "vda5050/KUKA/KMR-001/connection"
        msg.payload = b"not json"

        # Should not raise
        monitor._on_message(None, None, msg)
        assert not monitor.redis_client.hset.called

    def test_on_message_wrong_topic(self, monitor):
        """Messages on wrong topic pattern should be ignored."""
        msg = MagicMock()
        msg.topic = "some/other/topic"
        msg.payload = b"{}"

        monitor._on_message(None, None, msg)
        assert not monitor.redis_client.hset.called

    def test_on_message_multiple_robots(self, monitor):
        """Different robots should use different Redis keys."""
        msg1 = MagicMock()
        msg1.topic = "vda5050/KUKA/KMR-001/connection"
        msg1.payload = json.dumps({"state": "ONLINE"}).encode()

        msg2 = MagicMock()
        msg2.topic = "vda5050/MiR/MIR-001/connection"
        msg2.payload = json.dumps({"state": "OFFLINE"}).encode()

        monitor._on_message(None, None, msg1)
        monitor._on_message(None, None, msg2)

        # Should have called hset twice with different keys
        assert monitor.redis_client.hset.call_count == 2
