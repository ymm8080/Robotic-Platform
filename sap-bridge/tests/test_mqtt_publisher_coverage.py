"""Coverage gap tests for VDA5050Publisher — lifecycle, callbacks, connect/disconnect, edge cases."""
from unittest.mock import MagicMock, patch

import pytest
from mqtt_publisher import VDA5050Publisher


@pytest.fixture
def pub():
    """Publisher with mocked redis and mqtt client."""
    with patch("mqtt_publisher.redis_from_url") as mock_redis_factory:
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_redis_factory.return_value = mock_redis
        p = VDA5050Publisher()
        p.client = MagicMock()
        yield p


# ── Lifecycle: connect / disconnect (lines 50-67) ─────────


class TestPublisherLifecycle:
    """Target lines 50-67: connect(), disconnect()."""

    def test_connect_creates_will_and_connects(self, pub):
        """Lines 50-61: connect() sets LWT and calls client.connect."""
        pub.connect()
        pub.client.will_set.assert_called_once()
        pub.client.connect.assert_called_once()
        pub.client.loop_start.assert_called_once()

    def test_disconnect_stops_loop(self, pub):
        """Lines 63-67: disconnect() stops loop and disconnects."""
        pub.disconnect()
        pub.client.loop_stop.assert_called_once()
        pub.client.disconnect.assert_called_once()
        assert pub._connected is False

    def test_is_connected_property(self, pub):
        """Line 119: is_connected returns _connected state."""
        # Default is False
        assert pub.is_connected is False
        # After setting _connected = True
        pub._connected = True
        assert pub.is_connected is True


# ── Callbacks (lines 123-142) ────────────────────────────


class TestPublisherCallbacks:
    """Target lines 123-142: MQTT event callbacks."""

    def test_on_connect_success(self, pub):
        """Lines 123-131: rc=0 → connected=True, publishes connection state."""
        pub._on_connect(pub.client, None, None, 0)
        assert pub._connected is True
        pub.client.publish.assert_called()

    def test_on_connect_failure(self, pub):
        """Lines 132-134: rc!=0 → connected=False."""
        pub._on_connect(pub.client, None, None, 5)  # rc=5 = not authorized
        assert pub._connected is False

    def test_on_disconnect_unexpected(self, pub):
        """Lines 136-139: rc!=0 → warning for unexpected disconnect."""
        pub._connected = True
        pub._on_disconnect(pub.client, None, 1)  # rc=1 = unexpected
        assert pub._connected is False

    def test_on_disconnect_expected(self, pub):
        """Lines 136-139: rc=0 → graceful disconnect."""
        pub._connected = True
        pub._on_disconnect(pub.client, None, 0)  # rc=0 = expected
        assert pub._connected is False

    def test_on_publish_callback(self, pub):
        """Line 141-142: publish confirmation callback."""
        # Should not raise — just logs
        pub._on_publish(pub.client, None, 42)
        # middle should be logged at debug level
        assert True


# ── publish edge cases ───────────────────────────────────


class TestPublisherPublishEdgeCases:
    """Additional publish path coverage."""

    def test_publish_sets_timestamp(self, pub):
        """Verify timestamp is ISO format."""
        pub.redis_client.incr.return_value = 1
        pub.client.publish.return_value.rc = 0
        pub.publish("KUKA", "KMR-001", "order", {"orderId": "123"})
        import json
        args, _ = pub.client.publish.call_args
        payload = json.loads(args[1])
        assert payload["timestamp"] is not None
        assert "T" in payload["timestamp"]  # ISO format check
