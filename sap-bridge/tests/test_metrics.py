"""Tests for Metrics module — metric registration, labels, response."""
import importlib
import pytest

# Check if prometheus_client is available
HAS_PROMETHEUS = importlib.util.find_spec("prometheus_client") is not None


pytestmark = pytest.mark.skipif(not HAS_PROMETHEUS, reason="prometheus_client not installed")


class TestMetricsRegistry:
    """Metrics are registered as module-level objects with correct names."""

    def test_metrics_module_imports(self):
        from metrics import (orders_created, orders_completed, orders_failed,
                             mqtt_connected, redis_connected, sap_connected,
                             queue_depth, deadletter_unresolved,
                             http_requests, uptime)
        assert "sap_bridge_orders_created" in str(orders_created._name)
        assert "sap_bridge_orders_completed" in str(orders_completed._name)
        assert "sap_bridge_orders_failed" in str(orders_failed._name)
        assert "sap_bridge_mqtt_connected" in str(mqtt_connected._name)
        assert "sap_bridge_redis_connected" in str(redis_connected._name)
        assert "sap_bridge_sap_connected" in str(sap_connected._name)
        assert "sap_bridge_queue_depth" in str(queue_depth._name)
        assert "sap_bridge_deadletter_unresolved" in str(deadletter_unresolved._name)
        assert "sap_bridge_http_requests" in str(http_requests._name)
        assert "sap_bridge_uptime" in str(uptime._name)

    def test_orders_created_labels_inc(self):
        from metrics import orders_created
        orders_created.labels(type="PICK").inc()
        orders_created.labels(type="MOVE").inc(3)

    def test_orders_failed_labels_inc(self):
        from metrics import orders_failed
        orders_failed.labels(reason="timeout").inc(2)

class TestMetricsMiddleware:
    """Middleware tests — skipped without starlette."""

    @pytest.mark.skip(reason="MetricsMiddleware needs starlette")
    def test_middleware_skips_metrics_path(self):
        pass

    @pytest.mark.skip(reason="MetricsMiddleware needs starlette")
    def test_middleware_counts_non_metrics(self):
        pass

    def test_http_requests_labels_inc(self):
        from metrics import http_requests
        http_requests.labels(method="POST", path="/orders", status="200").inc()
        http_requests.labels(method="GET", path="/health", status="200").inc(5)

    def test_gauges_set_values(self):
        from metrics import mqtt_connected, redis_connected, queue_depth, deadletter_unresolved, sap_connected
        mqtt_connected.set(1)
        redis_connected.set(0)
        sap_connected.set(1)
        queue_depth.labels(priority="all").set(5)
        deadletter_unresolved.set(3)

    def test_uptime_counter(self):
        from metrics import uptime
        before = uptime._value.get()
        uptime.inc(100)
        after = uptime._value.get()
        assert after >= before


class TestMetricsResponse:
    """metrics_response should return valid Prometheus text."""

    def test_metrics_response_headers(self):
        from metrics import metrics_response
        resp = metrics_response()
        assert resp.media_type.startswith("text/plain")
        assert resp.headers.get("Cache-Control") == "no-cache"

    def test_metrics_response_contains_metric_names(self):
        from metrics import metrics_response
        resp = metrics_response()
        body = resp.body.decode()
        assert "sap_bridge_" in body
        assert "# HELP" in body
        assert "# TYPE" in body

    def test_metrics_response_includes_gauge_values(self):
        from metrics import metrics_response, mqtt_connected
        mqtt_connected.set(1)
        resp = metrics_response()
        body = resp.body.decode()
        assert "sap_bridge_mqtt_connected" in body
