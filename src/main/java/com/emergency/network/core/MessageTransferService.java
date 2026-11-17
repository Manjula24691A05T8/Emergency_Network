package com.emergency.network.core;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public final class MessageTransferService {
    public static final List<String> PRIORITIES = List.of("Critical", "High", "Medium", "Normal");
    private static final int IP_HEADER_BYTES = 64;

    public record EmergencyMessage(
            String messageId,
            int sequence,
            String source,
            String destination,
            String content,
            String priority,
            String queuedAt) {
        public EmergencyMessage {
            requireText(messageId, "Message id");
            requireText(source, "Message source");
            requireText(destination, "Message destination");
            requireText(content, "Message content");
            requireText(priority, "Message priority");
            requireText(queuedAt, "Queue timestamp");
            if (sequence < 1) {
                throw new IllegalArgumentException("Message sequence must be positive.");
            }
        }
    }

    public record PacketEvent(
            String packetId,
            String messageId,
            String sourceIp,
            String destinationIp,
            String protocol,
            int packetSizeBytes,
            String timestamp,
            String status,
            Double transmissionDelayMs,
            String priority,
            List<String> route) {
        public PacketEvent {
            requireText(packetId, "Packet id");
            requireText(messageId, "Message id");
            requireText(sourceIp, "Source address");
            requireText(destinationIp, "Destination address");
            requireText(protocol, "Protocol");
            requireText(timestamp, "Packet timestamp");
            requireText(status, "Packet status");
            requireText(priority, "Packet priority");
            if (packetSizeBytes < 1) {
                throw new IllegalArgumentException("Packet size must be positive.");
            }
            if (transmissionDelayMs != null
                    && (!Double.isFinite(transmissionDelayMs) || transmissionDelayMs < 0)) {
                throw new IllegalArgumentException("Transmission delay must be finite and non-negative.");
            }
            route = List.copyOf(route);
        }
    }

    private final PacketSimulationService packetSimulationService;

    public MessageTransferService() {
        this(new PacketSimulationService());
    }

    public MessageTransferService(PacketSimulationService packetSimulationService) {
        this.packetSimulationService =
                Objects.requireNonNull(packetSimulationService, "Packet simulation service");
    }

    public List<EmergencyMessage> enqueue(
            Iterable<EmergencyMessage> queue, EmergencyMessage message) {
        Objects.requireNonNull(queue, "Message queue");
        Objects.requireNonNull(message, "Message");
        validatePriority(message.priority());
        if (message.source().equals(message.destination())) {
            throw new IllegalArgumentException("Choose different sender and receiver services.");
        }
        if (message.content().isBlank()) {
            throw new IllegalArgumentException("Enter a message before queueing it.");
        }
        List<EmergencyMessage> messages = new ArrayList<>();
        queue.forEach(existing -> {
            if (existing == null) {
                throw new IllegalArgumentException("Message queue must not contain null entries.");
            }
            messages.add(existing);
        });
        messages.add(message);
        return orderMessages(messages);
    }

    public List<EmergencyMessage> orderMessages(Iterable<EmergencyMessage> queue) {
        Objects.requireNonNull(queue, "Message queue");
        List<EmergencyMessage> messages = new ArrayList<>();
        queue.forEach(message -> {
            if (message == null) {
                throw new IllegalArgumentException("Message queue must not contain null entries.");
            }
            validatePriority(message.priority());
            messages.add(message);
        });
        messages.sort(Comparator
                .comparingInt((EmergencyMessage message) -> PRIORITIES.indexOf(message.priority()))
                .thenComparingInt(EmergencyMessage::sequence));
        return List.copyOf(messages);
    }

    public PacketEvent processMessage(
            NetworkTopology.Topology topology, EmergencyMessage message) {
        Objects.requireNonNull(topology, "Topology");
        Objects.requireNonNull(message, "Message");
        validatePriority(message.priority());
        NetworkTopology.Node source = topology.node(message.source());
        NetworkTopology.Node destination = topology.node(message.destination());
        if (source == null || destination == null) {
            throw new IllegalArgumentException(
                    "Message endpoints must exist in the current topology.");
        }
        if (message.source().equals(message.destination())) {
            throw new IllegalArgumentException("Choose different sender and receiver services.");
        }
        int packetSize = Math.addExact(
                message.content().getBytes(java.nio.charset.StandardCharsets.UTF_8).length,
                IP_HEADER_BYTES);
        String packetId = "PKT-%06d".formatted(message.sequence());
        String timestamp = OffsetDateTime.now().toString();
        try {
            PacketSimulationService.TransmissionPlan plan =
                    packetSimulationService.createTransmissionPlan(
                            topology, message.source(), message.destination(), message.content());
            return new PacketEvent(
                    packetId,
                    message.messageId(),
                    source.address(),
                    destination.address(),
                    "Emergency DATA/ACK",
                    plan.packetSizeBytes(),
                    timestamp,
                    "Delivered",
                    plan.estimatedDeliveryDelayMs(),
                    message.priority(),
                    plan.route());
        } catch (PacketSimulationService.NoRouteException exception) {
            return new PacketEvent(
                    packetId,
                    message.messageId(),
                    source.address(),
                    destination.address(),
                    "Emergency DATA/ACK",
                    packetSize,
                    timestamp,
                    "Failed: no active route",
                    null,
                    message.priority(),
                    List.of());
        }
    }

    private static void validatePriority(String priority) {
        if (!PRIORITIES.contains(priority)) {
            throw new IllegalArgumentException("Choose a supported emergency priority.");
        }
    }

    private static void requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank.");
        }
    }
}
