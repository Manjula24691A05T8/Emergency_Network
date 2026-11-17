package com.emergency.network.core;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class DistanceVectorService {
    public record RouteEntry(Double cost, String nextHop) {}

    public record Snapshot(int roundNumber, Map<String, Map<String, RouteEntry>> tables) {
        public Snapshot {
            tables = immutableTables(tables);
        }
    }

    public record Result(
            Map<String, Map<String, RouteEntry>> tables,
            List<Snapshot> history,
            boolean converged) {
        public Result {
            tables = immutableTables(tables);
            history = List.copyOf(history);
            if (history.isEmpty()) {
                throw new IllegalArgumentException("Distance Vector history must not be empty.");
            }
        }

        public int convergenceRound() {
            return history.get(history.size() - 1).roundNumber();
        }
    }

    public Result simulate(NetworkTopology.Topology topology) {
        Objects.requireNonNull(topology, "Topology");
        List<String> nodes = topology.activeNodes().stream()
                .map(NetworkTopology.Node::id)
                .toList();
        Map<String, List<NetworkTopology.Link>> adjacency = new LinkedHashMap<>();
        nodes.forEach(node -> adjacency.put(node, new ArrayList<>()));
        for (NetworkTopology.Link link : topology.links().values()) {
            if (link.status() != NetworkTopology.Status.ACTIVE) {
                continue;
            }
            if (!adjacency.containsKey(link.first()) || !adjacency.containsKey(link.second())) {
                continue;
            }
            if (!Double.isFinite(link.delayMs()) || link.delayMs() < 0) {
                throw new IllegalArgumentException(
                        "Active link " + link.first() + "–" + link.second()
                                + " needs a finite, non-negative delay_ms cost.");
            }
            adjacency.get(link.first()).add(link);
            adjacency.get(link.second()).add(link);
        }

        Map<String, Map<String, Double>> costs = new LinkedHashMap<>();
        Map<String, Map<String, String>> nextHops = new LinkedHashMap<>();
        for (String node : nodes) {
            Map<String, Double> nodeCosts = new LinkedHashMap<>();
            Map<String, String> nodeHops = new LinkedHashMap<>();
            for (String destination : nodes) {
                nodeCosts.put(destination, node.equals(destination) ? 0.0 : Double.POSITIVE_INFINITY);
                nodeHops.put(destination, null);
            }
            for (NetworkTopology.Link link : adjacency.get(node)) {
                String neighbor = link.first().equals(node) ? link.second() : link.first();
                nodeCosts.put(neighbor, link.delayMs());
                nodeHops.put(neighbor, neighbor);
            }
            costs.put(node, nodeCosts);
            nextHops.put(node, nodeHops);
        }

        List<Snapshot> history = new ArrayList<>();
        history.add(snapshot(0, nodes, costs, nextHops));
        boolean converged = false;
        int maxRounds = Math.max(1, nodes.size());
        for (int round = 1; round <= maxRounds; round++) {
            Map<String, Map<String, Double>> updatedCosts = copyCosts(costs);
            Map<String, Map<String, String>> updatedHops = copyHops(nextHops);
            boolean changed = false;
            for (String node : nodes) {
                for (String destination : nodes) {
                    for (NetworkTopology.Link link : adjacency.get(node)) {
                        String neighbor = link.first().equals(node) ? link.second() : link.first();
                        double neighborCost = costs.get(neighbor).get(destination);
                        if (!Double.isFinite(neighborCost)) {
                            continue;
                        }
                        double candidate = link.delayMs() + neighborCost;
                        if (candidate < updatedCosts.get(node).get(destination)) {
                            updatedCosts.get(node).put(destination, candidate);
                            updatedHops.get(node).put(destination, neighbor);
                            changed = true;
                        }
                    }
                }
            }
            costs = updatedCosts;
            nextHops = updatedHops;
            history.add(snapshot(round, nodes, costs, nextHops));
            if (!changed) {
                converged = true;
                break;
            }
        }
        Snapshot latest = history.get(history.size() - 1);
        return new Result(latest.tables(), history, converged);
    }

    public List<String> path(Result result, String source, String destination) {
        Objects.requireNonNull(result, "Distance Vector result");
        Map<String, RouteEntry> sourceTable = result.tables().get(source);
        if (sourceTable == null || !sourceTable.containsKey(destination)) {
            throw new IllegalArgumentException(
                    "Source and destination must be active nodes in the routing tables.");
        }
        if (sourceTable.get(destination).cost() == null) {
            return List.of();
        }
        List<String> path = new ArrayList<>();
        Set<String> visited = new HashSet<>();
        String current = source;
        path.add(current);
        visited.add(current);
        for (int hop = 0; hop < result.tables().size(); hop++) {
            if (current.equals(destination)) {
                return List.copyOf(path);
            }
            RouteEntry route = result.tables().get(current).get(destination);
            String nextHop = route == null ? null : route.nextHop();
            if (nextHop == null || !visited.add(nextHop)) {
                throw new IllegalStateException(
                        "Converged routing tables contain an invalid next-hop chain.");
            }
            path.add(nextHop);
            current = nextHop;
        }
        throw new IllegalStateException("Distance Vector path exceeded the active node count.");
    }

    private static Snapshot snapshot(
            int round,
            List<String> nodes,
            Map<String, Map<String, Double>> costs,
            Map<String, Map<String, String>> nextHops) {
        Map<String, Map<String, RouteEntry>> tables = new LinkedHashMap<>();
        for (String node : nodes) {
            Map<String, RouteEntry> destinations = new LinkedHashMap<>();
            for (String destination : nodes) {
                double cost = costs.get(node).get(destination);
                destinations.put(destination, new RouteEntry(
                        Double.isFinite(cost) ? cost : null,
                        nextHops.get(node).get(destination)));
            }
            tables.put(node, destinations);
        }
        return new Snapshot(round, tables);
    }

    private static Map<String, Map<String, Double>> copyCosts(
            Map<String, Map<String, Double>> source) {
        Map<String, Map<String, Double>> copy = new LinkedHashMap<>();
        source.forEach((node, values) -> copy.put(node, new LinkedHashMap<>(values)));
        return copy;
    }

    private static Map<String, Map<String, String>> copyHops(
            Map<String, Map<String, String>> source) {
        Map<String, Map<String, String>> copy = new LinkedHashMap<>();
        source.forEach((node, values) -> copy.put(node, new LinkedHashMap<>(values)));
        return copy;
    }

    private static Map<String, Map<String, RouteEntry>> immutableTables(
            Map<String, Map<String, RouteEntry>> tables) {
        Objects.requireNonNull(tables, "Routing tables");
        Map<String, Map<String, RouteEntry>> copy = new LinkedHashMap<>();
        tables.forEach((node, destinations) -> copy.put(
                node,
                Collections.unmodifiableMap(new LinkedHashMap<>(destinations))));
        return Collections.unmodifiableMap(copy);
    }
}
