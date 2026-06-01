from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        CollectorRegistry,
        generate_latest,
    )

    MEMORY_REGISTRY = CollectorRegistry()

    memory_events_total = Counter(
        "memory_events_total",
        "Total memory events written",
        ["event_type", "status"],
        registry=MEMORY_REGISTRY,
    )

    memory_retrieval_latency = Histogram(
        "memory_retrieval_latency_seconds",
        "Memory retrieval latency",
        ["source"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
        registry=MEMORY_REGISTRY,
    )

    memory_buffer_size = Gauge(
        "memory_buffer_size",
        "Current event buffer size",
        registry=MEMORY_REGISTRY,
    )

    memory_classification_latency = Histogram(
        "memory_classification_latency_seconds",
        "LLM classification latency",
        buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
        registry=MEMORY_REGISTRY,
    )

    memory_db_write_errors = Counter(
        "memory_db_write_errors_total",
        "Database write error count",
        registry=MEMORY_REGISTRY,
    )

    METRICS_AVAILABLE = True

except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("prometheus_client 未安装，A03 指标不可用")

    class _NoopMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, amount=1):
            pass

        def set(self, value):
            pass

        def observe(self, value):
            pass

    MEMORY_REGISTRY = None
    memory_events_total = _NoopMetric()
    memory_retrieval_latency = _NoopMetric()
    memory_buffer_size = _NoopMetric()
    memory_classification_latency = _NoopMetric()
    memory_db_write_errors = _NoopMetric()


def get_metrics_response() -> bytes:
    if not METRICS_AVAILABLE:
        return b"# prometheus_client not installed\n"
    return generate_latest(MEMORY_REGISTRY)