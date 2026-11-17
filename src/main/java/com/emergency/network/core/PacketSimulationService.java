package com.emergency.network.core;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;

public final class PacketSimulationService {
    private static final int IP_HEADER_BYTES = 64;
    private static final int ACK_BYTES = 64;

    public record TransmissionPlan(
            String source,
            String destination,
            String message,
            List<String> route,
            int packetSizeBytes,
            double oneWayDelayMs,
            double acknowledgementDelayMs,
            double estimatedDeliveryDelayMs,
            int retransmissions) {
        public TransmissionPlan {
            route = List.copyOf(route);
        }
    }

    public static final class NoRouteException extends IllegalArgumentException {
        public NoRouteException(String source, String destination) {
            super("No active route from " + source + " to " + destination + ".");
        }
    }

    private record QueueEntry(String node, double cost) {}

    public TransmissionPlan createTransmissionPlan(
            NetworkTopology.Topology topology,
            String source,
            String destination,
            String message) {
        return createTransmissionPlan(topology, source, destination, message, false);
    }

    public TransmissionPlan createTransmissionPlan(
            NetworkTopology.Topology topology,
            String source,
            String destination,
            String message,
            boolean injectPacketLoss) {
        Objects.requireNonNull(topology, "Topology");
        if (!topology.nodes().containsKey(source) || !topology.nodes().containsKey(destination)) {
            throw new IllegalArgumentException("Source and destination must be nodes in the topology.");
        }
        if (source.equals(destination)) {
            throw new IllegalArgumentException("Choose different source and destination devices.");
        }
        if (topology.node(source).status() != NetworkTopology.Status.ACTIVE
                || topology.node(destination).status() != NetworkTopology.Status.ACTIVE) {
            throw new NoRouteException(source, destination);
        }
        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException("Enter a message before preparing a transmission.");
        }

        int packetSize = Math.addExact(message.getBytes(StandardCharsets.UTF_8).length, IP_HEADER_BYTES);
        List<String> route = shortestRoute(topology, source, destination, packetSize);
        double oneWayDelay = pathDelay(topology, route, packetSize);
        List<String> reverseRoute = new ArrayList<>(route);
        java.util.Collections.reverse(reverseRoute);
        double acknowledgementDelay = pathDelay(topology, reverseRoute, ACK_BYTES);
        int retransmissions = injectPacketLoss ? 1 : 0;
        double failedAttemptDelay = injectPacketLoss
                ? linkDelay(topology.link(route.get(0), route.get(1)), packetSize) / 2.0
                : 0.0;
        return new TransmissionPlan(
                source,
                destination,
                message,
                route,
                packetSize,
                oneWayDelay,
                acknowledgementDelay,
                failedAttemptDelay + oneWayDelay + acknowledgementDelay,
                retransmissions);
    }

    private static List<String> shortestRoute(
            NetworkTopology.Topology topology, String source, String destination, int packetSize) {
        Map<String, Double> distances = new HashMap<>();
        Map<String, String> previous = new HashMap<>();
        PriorityQueue<QueueEntry> pending = new PriorityQueue<>(
                Comparator.comparingDouble(QueueEntry::cost).thenComparing(QueueEntry::node));
        distances.put(source, 0.0);
        pending.add(new QueueEntry(source, 0.0));

        while (!pending.isEmpty()) {
            QueueEntry current = pending.remove();
            if (current.cost() > distances.getOrDefault(current.node(), Double.POSITIVE_INFINITY)) {
                continue;
            }
            if (current.node().equals(destination)) {
                break;
            }
            for (NetworkTopology.Link link : topology.links().values()) {
                if (link.status() != NetworkTopology.Status.ACTIVE) {
                    continue;
                }
                String neighbor;
                if (link.first().equals(current.node())) {
                    neighbor = link.second();
                } else if (link.second().equals(current.node())) {
                    neighbor = link.first();
                } else {
                    continue;
                }
                if (topology.node(neighbor).status() != NetworkTopology.Status.ACTIVE) {
                    continue;
                }
                double candidate = current.cost() + linkDelay(link, packetSize);
                if (candidate < distances.getOrDefault(neighbor, Double.POSITIVE_INFINITY)) {
                    distances.put(neighbor, candidate);
                    previous.put(neighbor, current.node());
                    pending.add(new QueueEntry(neighbor, candidate));
                }
            }
        }
        if (!distances.containsKey(destination)) {
            throw new NoRouteException(source, destination);
        }
        List<String> route = new ArrayList<>();
        for (String node = destination; node != null; node = previous.get(node)) {
            route.add(node);
            if (node.equals(source)) {
                break;
            }
        }
        java.util.Collections.reverse(route);
        if (route.isEmpty() || !route.get(0).equals(source)) {
            throw new NoRouteException(source, destination);
        }
        return List.copyOf(route);
    }

    private static double pathDelay(
            NetworkTopology.Topology topology, List<String> route, int packetSizeBytes) {
        double delay = 0.0;
        for (int index = 0; index + 1 < route.size(); index++) {
            delay += linkDelay(topology.link(route.get(index), route.get(index + 1)), packetSizeBytes);
        }
        return delay;
    }

    private static double linkDelay(NetworkTopology.Link link, int packetSizeBytes) {
        if (link == null || link.status() != NetworkTopology.Status.ACTIVE) {
            throw new IllegalArgumentException("Route contains a non-active link.");
        }
        double serializationDelayMs =
                packetSizeBytes * 8.0 / (link.bandwidthMbps() * 1_000_000.0) * 1_000.0;
        return link.delayMs() + serializationDelayMs;
    }
}
