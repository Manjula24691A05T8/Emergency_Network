from dataclasses import dataclass
from typing import Iterable

from modules.message_transfer import PacketEvent


@dataclass(frozen=True)
class PerformanceSummary:
    total_packets: int
    delivered_packets: int
    failed_packets: int
    packet_delivery_ratio_percent: float | None
    packet_loss_ratio_percent: float | None
    average_delay_ms: float | None
    modeled_throughput_mbps: float | None


def summarize_packet_events(events: Iterable[PacketEvent]) -> PerformanceSummary:
    records = list(events)
    delivered = [event for event in records if event.status == "Delivered"]
    failed_count = len(records) - len(delivered)
    total_count = len(records)
    delays = [
        event.transmission_delay_ms
        for event in delivered
        if event.transmission_delay_ms is not None
    ]
    total_delay_ms = sum(delays)
    delivered_bits = sum(event.packet_size_bytes * 8 for event in delivered)

    return PerformanceSummary(
        total_packets=total_count,
        delivered_packets=len(delivered),
        failed_packets=failed_count,
        packet_delivery_ratio_percent=(
            100 * len(delivered) / total_count if total_count else None
        ),
        packet_loss_ratio_percent=(
            100 * failed_count / total_count if total_count else None
        ),
        average_delay_ms=(sum(delays) / len(delays) if delays else None),
        modeled_throughput_mbps=(
            delivered_bits / (total_delay_ms * 1000)
            if total_delay_ms > 0
            else None
        ),
    )
