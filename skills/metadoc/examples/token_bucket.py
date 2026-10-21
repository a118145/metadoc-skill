"""Token-bucket rate limiter with an injectable clock."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TokenBucket:
    """Allows bursts of up to `capacity` events and `rate` events per second on average."""

    rate: float
    capacity: float
    clock: Callable[[], float] = time.monotonic
    tokens: float = field(init=False)
    stamp: float = field(init=False)

    def __post_init__(self) -> None:
        if self.rate <= 0 or self.capacity <= 0:
            raise ValueError("rate and capacity must be positive")
        self.tokens = self.capacity
        self.stamp = self.clock()

    # Tokens are topped up lazily, only when someone asks, so an idle bucket costs nothing.
    def _refill(self) -> None:
        now = self.clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.stamp) * self.rate)
        self.stamp = now

    def try_acquire(self, cost: float = 1.0) -> bool:
        if cost > self.capacity:
            raise ValueError("cost exceeds capacity and could never be granted")
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def wait_time(self, cost: float = 1.0) -> float:
        self._refill()
        missing = cost - self.tokens
        return max(0.0, missing / self.rate)


class FakeClock:
    """Manually advanced clock for deterministic tests and demos."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


if __name__ == "__main__":
    clock = FakeClock()
    bucket = TokenBucket(rate=2.0, capacity=3.0, clock=clock)
    for _ in range(8):
        print(f"t={clock.now:.2f}s granted={bucket.try_acquire()} wait={bucket.wait_time():.2f}s")
        clock.now += 0.25
