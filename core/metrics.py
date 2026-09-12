from prometheus_client import CollectorRegistry, Gauge, Histogram

registry = CollectorRegistry()

queue_jobs = Gauge(
    "undarr_queue_jobs",
    "Current queue depth by status",
    ["status"],
    registry=registry,
)

device_active_jobs = Gauge(
    "undarr_device_active_jobs",
    "Active jobs per device",
    ["device"],
    registry=registry,
)

queue_paused = Gauge(
    "undarr_queue_paused",
    "1 if queue is globally paused, 0 otherwise",
    registry=registry,
)

jobs_by_result = Gauge(
    "undarr_jobs",
    "Job history counts by result",
    ["result"],
    registry=registry,
)

space_saved_bytes = Gauge(
    "undarr_space_saved_bytes",
    "Total bytes saved by completed transcodes",
    registry=registry,
)

transcode_duration = Histogram(
    "undarr_transcode_duration_seconds",
    "Distribution of transcode durations",
    buckets=(30, 60, 120, 300, 600, 1800, 3600, 7200, float("inf")),
    registry=registry,
)

libraries = Gauge(
    "undarr_libraries",
    "Number of configured libraries",
    registry=registry,
)
