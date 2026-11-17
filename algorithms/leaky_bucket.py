from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class LeakyBucketStep:
    tick: int
    arrivals: int
    admitted: int
    queued_before_leak: int
    transmitted: int
    dropped: int
    queued_after_leak: int


@dataclass(frozen=True)
class LeakyBucketResult:
    capacity: int
    output_rate: int
    steps: tuple[LeakyBucketStep, ...]

    @property
    def total_arrivals(self) -> int:
        return sum(step.arrivals for step in self.steps)

    @property
    def total_admitted(self) -> int:
        return sum(step.admitted for step in self.steps)

    @property
    def total_transmitted(self) -> int:
        return sum(step.transmitted for step in self.steps)

    @property
    def total_dropped(self) -> int:
        return sum(step.dropped for step in self.steps)

    @property
    def peak_occupancy(self) -> int:
        return max(step.queued_before_leak for step in self.steps)

    @property
    def congested_slots(self) -> int:
        return sum(
            step.dropped > 0 or step.queued_before_leak == self.capacity
            for step in self.steps
        )

    @property
    def congestion_rate_percent(self) -> float:
        return self.congested_slots / len(self.steps) * 100

    @property
    def congestion_status(self) -> str:
        if self.total_dropped:
            return "Congested"
        if self.peak_occupancy == self.capacity:
            return "At capacity"
        return "Stable"


def simulate_leaky_bucket(
    arrivals: Sequence[int],
    capacity: int,
    output_rate: int,
) -> LeakyBucketResult:
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("Bucket capacity must be a positive integer.")
    if not isinstance(output_rate, int) or isinstance(output_rate, bool) or output_rate < 1:
        raise ValueError("Output rate must be a positive integer.")
    if not arrivals:
        raise ValueError("Provide at least one time slot of incoming traffic.")
    if any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in arrivals
    ):
        raise ValueError("Arrivals must be non-negative integers.")

    queued = 0
    steps = []
    for tick, incoming in enumerate(arrivals, start=1):
        admitted = min(incoming, capacity - queued)
        dropped = incoming - admitted
        queued += admitted
        queued_before_leak = queued
        transmitted = min(output_rate, queued)
        queued -= transmitted
        steps.append(
            LeakyBucketStep(
                tick=tick,
                arrivals=incoming,
                admitted=admitted,
                queued_before_leak=queued_before_leak,
                transmitted=transmitted,
                dropped=dropped,
                queued_after_leak=queued,
            )
        )

    return LeakyBucketResult(
        capacity=capacity,
        output_rate=output_rate,
        steps=tuple(steps),
    )


def compare_leaky_bucket_profiles(
    arrivals: Sequence[int],
    capacity: int,
    normal_output_rate: int,
    stress_output_rate: int,
) -> tuple[LeakyBucketResult, LeakyBucketResult]:
    normal = simulate_leaky_bucket(arrivals, capacity, normal_output_rate)
    stress = simulate_leaky_bucket(arrivals, capacity, stress_output_rate)
    if stress_output_rate >= normal_output_rate:
        raise ValueError(
            "The congestion-stress output rate must be lower than the normal rate."
        )
    return normal, stress
