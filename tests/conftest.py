import pytest
from app.core.ratelimit import reset_rate_limits


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """All tests share one process-wide rate-limit bucket; reset between tests."""
    reset_rate_limits()
    yield
    reset_rate_limits()
