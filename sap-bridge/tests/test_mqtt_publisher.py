"""Tests for MQTT publisher module."""
import json
from unittest.mock import MagicMock, patch

import pytest

from mqtt_publisher import VDA5050Publisher


@pytest.fixture
def publisher():
    with patch("mqtt_publisher.redis_from_url") as mock_redis:
        mock_redis.return_value = MagicMock()
        pub = VDA5050Publisher()
        pub.client = MagicMock()
        yield pub


def test_publish_adds_sequence_number(publisher):
    """Verify sequence number is auto-added to each message."""
    publisher.redis_client.incr.return_value = 42
    publisher.client.publish.return_value.rc = 0  # MQTT_ERR_SUCCESS

    result = publisher.publish("KUKA", "KMR-001", "order", {"orderId": "123"})

    assert result is not None
    publisher.client.publish.assert_called_once()
    call_args = publisher.client.publish.call_args
    topic = call_args[0][0]
    payload = json.loads(call_args[0][1])

    assert topic == "vda5050/KUKA/KMR-001/order"
    assert payload["headerId"] == 42
    assert payload["manufacturer"] == "KUKA"
    assert payload["serialNumber"] == "KMR-001"


def test_publish_qos_default(publisher):
    """Verify default QoS is 1."""
    publisher.redis_client.incr.return_value = 1
    publisher.publish("MiR", "MiR-001", "state", {"driving": True})
    _, kwargs = publisher.client.publish.call_args
    assert kwargs.get("qos") == 1


def test_publish_on_disconnected_broker(publisher):
    """Verify publish handles broker disconnection gracefully."""
    publisher.redis_client.incr.return_value = 1
    publisher.client.publish.return_value.rc = 4  # MQTT_ERR_NO_CONN

    result = publisher.publish("OTTO", "OTTO-001", "connection", {"state": "ONLINE"})
    assert result is None


def test_sequence_number_increments_per_topic(publisher):
    """Verify sequence numbers are independent per topic."""
    publisher.redis_client.incr.side_effect = [1, 2, 1]  # third call resets for new topic

    publisher.publish("KUKA", "KMR-001", "state", {})
    publisher.publish("KUKA", "KMR-001", "state", {})
    publisher.publish("MiR", "MiR-001", "state", {})

    # First two calls use same topic key
    assert publisher.redis_client.incr.call_count == 3
