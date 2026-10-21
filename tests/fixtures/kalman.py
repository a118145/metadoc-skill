"""One-dimensional constant-velocity Kalman filter with a small simulation driver."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class GaussianState:
    """Mean and covariance of the filter state [position, velocity]."""

    mean: list[float] = field(default_factory=lambda: [0.0, 0.0])
    covariance: list[list[float]] = field(
        default_factory=lambda: [[1000.0, 0.0], [0.0, 1000.0]]
    )


class KalmanFilter:
    """Tracks position and velocity from noisy position measurements."""

    def __init__(self, dt: float, process_noise: float, measurement_noise: float) -> None:
        self.dt = dt
        self.q = process_noise
        self.r = measurement_noise
        self.state = GaussianState()

    def predict(self) -> None:
        dt = self.dt
        (p, v) = self.state.mean
        self.state.mean = [p + dt * v, v]

        (a, b), (c, d) = self.state.covariance
        # P = F P F^T + Q with F = [[1, dt], [0, 1]] and white-acceleration noise Q.
        q = self.q
        self.state.covariance = [
            [a + dt * (b + c) + dt * dt * d + q * dt**4 / 4, b + dt * d + q * dt**3 / 2],
            [c + dt * d + q * dt**3 / 2, d + q * dt * dt],
        ]

    def update(self, measurement: float) -> float:
        (p, v) = self.state.mean
        (a, b), (c, d) = self.state.covariance

        innovation = measurement - p
        innovation_variance = a + self.r
        gain = [a / innovation_variance, c / innovation_variance]

        self.state.mean = [p + gain[0] * innovation, v + gain[1] * innovation]
        self.state.covariance = [
            [(1 - gain[0]) * a, (1 - gain[0]) * b],
            [c - gain[1] * a, d - gain[1] * b],
        ]
        return innovation

    @property
    def position(self) -> float:
        return self.state.mean[0]


def simulate(steps: int = 50, seed: int = 1) -> list[tuple[float, float, float]]:
    """Runs the filter on a synthetic track and returns (truth, measurement, estimate) per step."""
    rng = random.Random(seed)
    kf = KalmanFilter(dt=0.1, process_noise=0.5, measurement_noise=4.0)
    truth, velocity = 0.0, 1.5
    history = []
    for _ in range(steps):
        velocity += rng.gauss(0.0, 0.05)
        truth += velocity * kf.dt
        measurement = truth + rng.gauss(0.0, 2.0)
        kf.predict()
        kf.update(measurement)
        history.append((truth, measurement, kf.position))
    return history


if __name__ == "__main__":
    for truth, measurement, estimate in simulate():
        print(f"{truth:8.3f} {measurement:8.3f} {estimate:8.3f}")
