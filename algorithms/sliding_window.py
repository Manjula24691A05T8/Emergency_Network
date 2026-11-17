from dataclasses import dataclass


@dataclass(frozen=True)
class SlidingWindowBatch:
    round_number: int
    base_sequence: int
    transmitted: tuple[int, ...]
    acknowledged: tuple[int, ...]
    base_after_ack: int


@dataclass(frozen=True)
class SlidingWindowResult:
    packet_count: int
    window_size: int
    batches: tuple[SlidingWindowBatch, ...]

    @property
    def total_acknowledged(self) -> int:
        return sum(len(batch.acknowledged) for batch in self.batches)


def simulate_sliding_window(
    packet_count: int,
    window_size: int,
) -> SlidingWindowResult:
    if not isinstance(packet_count, int) or isinstance(packet_count, bool) or packet_count < 1:
        raise ValueError("Packet count must be a positive integer.")
    if not isinstance(window_size, int) or isinstance(window_size, bool) or window_size < 1:
        raise ValueError("Window size must be a positive integer.")

    batches = []
    base = 1
    round_number = 1
    while base <= packet_count:
        window_end = min(base + window_size - 1, packet_count)
        transmitted = tuple(range(base, window_end + 1))
        batches.append(
            SlidingWindowBatch(
                round_number=round_number,
                base_sequence=base,
                transmitted=transmitted,
                acknowledged=transmitted,
                base_after_ack=window_end + 1,
            )
        )
        base = window_end + 1
        round_number += 1

    return SlidingWindowResult(
        packet_count=packet_count,
        window_size=window_size,
        batches=tuple(batches),
    )
