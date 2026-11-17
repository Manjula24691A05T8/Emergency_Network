package com.emergency.network.core;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class PerformanceService {
    public record Summary(
            int totalPackets,
            int deliveredPackets,
            int failedPackets,
            Double packetDeliveryRatioPercent,
            Double packetLossRatioPercent,
            Double averageDelayMs,
            Double modeledThroughputMbps) {}

    public Summary summarize(Iterable<MessageTransferService.PacketEvent> events) {
        Objects.requireNonNull(events, "Packet events");
        List<MessageTransferService.PacketEvent> records = new ArrayList<>();
        events.forEach(event -> {
            if (event == null) {
                throw new IllegalArgumentException("Packet events must not contain null entries.");
            }
            records.add(event);
        });
        List<MessageTransferService.PacketEvent> delivered = records.stream()
                .filter(event -> event.status().equals("Delivered"))
                .toList();
        int total = records.size();
        int failed = total - delivered.size();
        double totalDelay = delivered.stream()
                .map(MessageTransferService.PacketEvent::transmissionDelayMs)
                .filter(Objects::nonNull)
                .mapToDouble(Double::doubleValue)
                .sum();
        double deliveredBits = delivered.stream()
                .mapToDouble(event -> (double) event.packetSizeBytes() * 8.0)
                .sum();
        List<Double> delays = delivered.stream()
                .map(MessageTransferService.PacketEvent::transmissionDelayMs)
                .filter(Objects::nonNull)
                .toList();
        return new Summary(
                total,
                delivered.size(),
                failed,
                total == 0 ? null : 100.0 * delivered.size() / total,
                total == 0 ? null : 100.0 * failed / total,
                delays.isEmpty() ? null : delays.stream().mapToDouble(Double::doubleValue).average().orElseThrow(),
                totalDelay > 0 ? deliveredBits / (totalDelay * 1_000.0) : null);
    }
}
