from app.core import ratelimit as rl


class _Clock:
    def __init__(self, start=0.0):
        self.now = start

    def advance(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


def _patch_settings(monkeypatch, requests=5, window=10.0, enabled=True):
    class _S:
        rate_limit_enabled = enabled
        rate_limit_requests = requests
        rate_limit_window_seconds = window

    monkeypatch.setattr(rl, "get_settings", lambda: _S())


def test_allows_up_to_capacity_then_blocks(monkeypatch):
    rl.reset_rate_limits()
    clock = _Clock()
    monkeypatch.setattr(rl.time, "monotonic", clock)
    _patch_settings(monkeypatch, requests=3, window=10.0)

    for _ in range(3):
        allowed, retry_after = rl.check_rate_limit("same-client")
        assert allowed is True
        assert retry_after == 0.0

    allowed, retry_after = rl.check_rate_limit("same-client")
    assert allowed is False
    assert retry_after > 0


def test_refills_over_time(monkeypatch):
    rl.reset_rate_limits()
    clock = _Clock()
    monkeypatch.setattr(rl.time, "monotonic", clock)
    _patch_settings(monkeypatch, requests=2, window=10.0)  # refill: 0.2 tokens/sec

    assert rl.check_rate_limit("client-a")[0] is True
    assert rl.check_rate_limit("client-a")[0] is True
    assert rl.check_rate_limit("client-a")[0] is False  # empty

    clock.advance(5.0)  # +1 token
    assert rl.check_rate_limit("client-a")[0] is True
    assert rl.check_rate_limit("client-a")[0] is False


def test_separate_identities_have_separate_buckets(monkeypatch):
    rl.reset_rate_limits()
    clock = _Clock()
    monkeypatch.setattr(rl.time, "monotonic", clock)
    _patch_settings(monkeypatch, requests=1, window=10.0)

    assert rl.check_rate_limit("client-a")[0] is True
    assert rl.check_rate_limit("client-a")[0] is False
    # A different identity has its own full bucket, unaffected by client-a.
    assert rl.check_rate_limit("client-b")[0] is True


def test_disabled_rate_limit_always_allows(monkeypatch):
    rl.reset_rate_limits()
    _patch_settings(monkeypatch, requests=1, enabled=False)
    for _ in range(10):
        assert rl.check_rate_limit("client-x")[0] is True
