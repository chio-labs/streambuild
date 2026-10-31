"""Sensor domain constants."""

SENSORS_DIRECTORY_NAME: str = "sensors"
NODE_RESULTS_EVENT_SOURCE: str = "node_results"
INVOCATIONS_EVENT_SOURCE: str = "invocations"
DEFAULT_SENSOR_TIMEOUT_SECONDS: float = 60.0
DEFAULT_EVENT_BATCH_LIMIT: int = 50
DISPATCH_LEASE_NAME: str = "sensor_dispatch"
DEFAULT_DISPATCH_LEASE_TTL_SECONDS: float = 60.0
