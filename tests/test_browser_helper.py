from datetime import datetime

import pytest

from app.sourcing.base import SourcePaused
from app.sourcing.browser.helper import RateLimiter, in_quiet_hours


def test_quiet_hours_wraps_midnight():
    assert in_quiet_hours("23-07", datetime(2026, 1, 1, 23, 30))
    assert in_quiet_hours("23-07", datetime(2026, 1, 1, 3, 0))
    assert not in_quiet_hours("23-07", datetime(2026, 1, 1, 12, 0))
    assert in_quiet_hours("09-17", datetime(2026, 1, 1, 10, 0))
    assert not in_quiet_hours("", datetime(2026, 1, 1, 10, 0))


def test_rate_limiter_delays_and_caps():
    slept = []
    rl = RateLimiter(10, 10, 3, sleep=slept.append)
    rl.wait()
    rl.wait()
    assert len(slept) == 1 and 9.9 < slept[0] <= 10.0
    rl.wait()
    with pytest.raises(SourcePaused):
        rl.wait()
    assert rl.budget_left() == 0
