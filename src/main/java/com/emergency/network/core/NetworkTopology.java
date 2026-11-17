package com.emergency.network.core;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class NetworkTopology {
    public static final String CONTROL_CENTER = "control_center";
    public static final List<String> SERVICE_NODES = List.of(
            CONTROL_CENTER,
            "police_station",
            "fire_station",
            "ambulance_service",
            "rescue_team",
            "emergency_shelter");
    public static final List<String> ROUTER_NODES = List.of("router_a", "router_b");

    public enum Status {
        ACTIVE,
        FAILED
    }

    public record Node(
            String id,
            String label,
            String shortLabel,
            String kind,
            String role,
            String address,
            double x,
            double y,
            Status status) {
        public Node {
            requireText(id, "Node id");
            requireText(label, "Node label");
            requireText(shortLabel, "Node short label");
            requireText(kind, "Node kind");
            requireText(role, "Node role");
            requireText(address, "Node address");
            Objects.requireNonNull(status, "Node status");
            if (!Double.isFinite(x) || !Double.isFinite(y)) {
                throw new IllegalArgumentException("Node coordinates must be finite.");
            }
        }
    }

    public record LinkKey(String first, String second) {
        public LinkKey {
            requireText(first, "First link endpoint");
            requireText(second, "Second link endpoint");
            if (first.equals(second)) {
                throw new IllegalArgumentException("A link must connect two different nodes.");
            }
            if (first.compareTo(second) > 0) {
                String originalFirst = first;
                first = second;
                second = originalFirst;
            }
        }
    }

    public record Link(
            LinkKey key, int bandwidthMbps, double delayMs, Status status) {
        public Link {
            Objects.requireNonNull(key, "Link key");
            Objects.requireNonNull(status, "Link status");
            if (bandwidthMbps <= 0) {
                throw new IllegalArgumentException("Link bandwidth must be positive.");
            }
            if (!Double.isFinite(delayMs) || delayMs < 0) {
                throw new IllegalArgumentException("Link delay must be finite and non-negative.");
            }
        }

        public String first() {
            return key.first();
        }

        public String second() {
            return key.second();
        }
    }

    public record Topology(Map<String, Node> nodes, Map<LinkKey, Link> links) {
        public Topology {
            Objects.requireNonNull(nodes, "Nodes");
            Objects.requireNonNull(links, "Links");
            Map<String, Node> nodeCopy = new LinkedHashMap<>(nodes);
            Map<LinkKey, Link> linkCopy = new LinkedHashMap<>(links);
            nodeCopy.forEach((id, node) -> {
                if (id == null || node == null || !id.equals(node.id())) {
                    throw new IllegalArgumentException("Node map keys must match node ids.");
                }
            });
            linkCopy.forEach((key, link) -> {
                if (key == null || link == null || !key.equals(link.key())
                        || !nodeCopy.containsKey(key.first())
                        || !nodeCopy.containsKey(key.second())) {
                    throw new IllegalArgumentException(
                            "Each link must reference two known nodes and match its map key.");
                }
            });
            nodes = Collections.unmodifiableMap(nodeCopy);
            links = Collections.unmodifiableMap(linkCopy);
        }

        public Node node(String id) {
            return nodes.get(id);
        }

        public Link link(String first, String second) {
            return links.get(new LinkKey(first, second));
        }

        public List<Link> activeLinks() {
            return links.values().stream().filter(link -> link.status() == Status.ACTIVE).toList();
        }

        public List<Node> activeNodes() {
            return nodes.values().stream().filter(node -> node.status() == Status.ACTIVE).toList();
        }
    }

    public record TopologyMetrics(
            int totalNodes,
            int activeRouters,
            int activeSwitches,
            int activeConnections,
            int failedConnections,
            int reachableServices,
            int totalServices,
            String networkHealth) {}

    private record NodeDefinition(
            String id,
            String label,
            String shortLabel,
            String kind,
            String role,
            String address,
            double x,
            double y) {}

    private record LinkDefinition(String first, String second, int bandwidthMbps, double delayMs) {}

    private static final List<NodeDefinition> NODE_DEFINITIONS = List.of(
            new NodeDefinition(CONTROL_CENTER, "Emergency Control Center", "ECC", "service",
                    "Command and dispatch", "10.20.0.10", -3.2, 1.5),
            new NodeDefinition("police_station", "Police Station", "POLICE", "service",
                    "Public safety", "10.20.0.11", -3.2, 0.35),
            new NodeDefinition("fire_station", "Fire Station", "FIRE", "service",
                    "Fire and rescue", "10.20.0.12", -3.2, -0.8),
            new NodeDefinition("switch_north", "North Access Switch", "SW-N", "switch",
                    "Access layer", "10.20.10.2", -1.45, 0.35),
            new NodeDefinition("router_a", "Core Router A", "R-A", "router",
                    "Core routing", "10.20.255.1", 0.1, 1.05),
            new NodeDefinition("router_b", "Core Router B", "R-B", "router",
                    "Core routing", "10.20.255.2", 0.1, -0.45),
            new NodeDefinition("switch_south", "South Access Switch", "SW-S", "switch",
                    "Access layer", "10.20.20.2", 1.65, 0.3),
            new NodeDefinition("ambulance_service", "Ambulance Service", "EMS", "service",
                    "Medical response", "10.20.0.13", 3.35, 1.35),
            new NodeDefinition("rescue_team", "Rescue Team", "RESCUE", "service",
                    "Search and rescue", "10.20.0.14", 3.35, 0.25),
            new NodeDefinition("emergency_shelter", "Emergency Shelter", "SHELTER", "service",
                    "Relief coordination", "10.20.0.15", 3.35, -0.85));

    private static final List<LinkDefinition> LINK_DEFINITIONS = List.of(
            new LinkDefinition(CONTROL_CENTER, "switch_north", 1000, 1.2),
            new LinkDefinition("police_station", "switch_north", 100, 1.5),
            new LinkDefinition("fire_station", "switch_north", 100, 1.8),
            new LinkDefinition("ambulance_service", "switch_south", 100, 1.4),
            new LinkDefinition("rescue_team", "switch_south", 100, 1.7),
            new LinkDefinition("emergency_shelter", "switch_south", 100, 2.0),
            new LinkDefinition("switch_north", "router_a", 1000, 0.8),
            new LinkDefinition("switch_north", "router_b", 1000, 1.0),
            new LinkDefinition("router_a", "router_b", 10000, 0.5),
            new LinkDefinition("router_a", "switch_south", 1000, 0.9),
            new LinkDefinition("router_b", "switch_south", 1000, 0.8));

    public Topology buildEmergencyTopology() {
        return buildEmergencyTopology(List.of(), List.of());
    }

    public Topology buildEmergencyTopology(
            Collection<LinkKey> failedLinks, Collection<String> failedNodes) {
        Objects.requireNonNull(failedLinks, "Failed links");
        Objects.requireNonNull(failedNodes, "Failed nodes");
        Set<LinkKey> requestedLinks = new HashSet<>(failedLinks);
        Set<String> requestedNodes = new HashSet<>(failedNodes);
        Set<LinkKey> knownLinks = new HashSet<>();
        LINK_DEFINITIONS.forEach(
                definition -> knownLinks.add(new LinkKey(definition.first(), definition.second())));
        Set<LinkKey> unknownLinks = new LinkedHashSet<>(requestedLinks);
        unknownLinks.removeAll(knownLinks);
        if (!unknownLinks.isEmpty()) {
            throw new IllegalArgumentException("Unknown link failure(s): " + unknownLinks);
        }
        Set<String> unknownNodes = new LinkedHashSet<>(requestedNodes);
        unknownNodes.removeAll(ROUTER_NODES);
        if (!unknownNodes.isEmpty()) {
            throw new IllegalArgumentException("Unknown router failure(s): " + unknownNodes);
        }

        Map<String, Node> nodes = new LinkedHashMap<>();
        for (NodeDefinition definition : NODE_DEFINITIONS) {
            nodes.put(definition.id(), new Node(
                    definition.id(),
                    definition.label(),
                    definition.shortLabel(),
                    definition.kind(),
                    definition.role(),
                    definition.address(),
                    definition.x(),
                    definition.y(),
                    requestedNodes.contains(definition.id()) ? Status.FAILED : Status.ACTIVE));
        }
        Map<LinkKey, Link> links = new LinkedHashMap<>();
        for (LinkDefinition definition : LINK_DEFINITIONS) {
            LinkKey key = new LinkKey(definition.first(), definition.second());
            boolean failed = requestedLinks.contains(key)
                    || requestedNodes.contains(definition.first())
                    || requestedNodes.contains(definition.second());
            links.put(key, new Link(
                    key,
                    definition.bandwidthMbps(),
                    definition.delayMs(),
                    failed ? Status.FAILED : Status.ACTIVE));
        }
        return new Topology(nodes, links);
    }

    public List<List<String>> availablePaths(
            Topology topology, String source, String destination, int limit, int maxHops) {
        Objects.requireNonNull(topology, "Topology");
        if (limit < 1 || maxHops < 1) {
            throw new IllegalArgumentException("Path limit and maximum hops must be positive.");
        }
        if (!topology.nodes().containsKey(source) || !topology.nodes().containsKey(destination)) {
            throw new IllegalArgumentException("Source and destination must be nodes in the topology.");
        }
        if (source.equals(destination)) {
            return List.of(List.of(source));
        }
        List<List<String>> paths = new ArrayList<>();
        List<String> current = new ArrayList<>();
        Set<String> visited = new HashSet<>();
        current.add(source);
        visited.add(source);
        findPaths(topology, source, destination, maxHops, limit, visited, current, paths);
        return paths.stream().map(List::copyOf).toList();
    }

    public List<List<String>> availablePaths(Topology topology, String source, String destination) {
        return availablePaths(topology, source, destination, 4, 6);
    }

    public TopologyMetrics metrics(Topology topology) {
        Objects.requireNonNull(topology, "Topology");
        Set<String> reachable = reachableFromControlCenter(topology);
        int failedConnections = (int) topology.links().values().stream()
                .filter(link -> link.status() != Status.ACTIVE)
                .count();
        int activeRouters = (int) topology.nodes().values().stream()
                .filter(node -> node.kind().equals("router") && node.status() == Status.ACTIVE)
                .count();
        int activeSwitches = (int) topology.nodes().values().stream()
                .filter(node -> node.kind().equals("switch") && node.status() == Status.ACTIVE)
                .count();
        int reachableServices = (int) SERVICE_NODES.stream().filter(reachable::contains).count();
        boolean hasUnreachableServices = reachableServices < SERVICE_NODES.size();
        String health = hasUnreachableServices
                ? "Critical"
                : failedConnections > 0 ? "Degraded" : "Operational";
        return new TopologyMetrics(
                topology.nodes().size(),
                activeRouters,
                activeSwitches,
                topology.links().size() - failedConnections,
                failedConnections,
                reachableServices,
                SERVICE_NODES.size(),
                health);
    }

    private static void findPaths(
            Topology topology,
            String currentNode,
            String destination,
            int maxHops,
            int limit,
            Set<String> visited,
            List<String> current,
            List<List<String>> paths) {
        if (paths.size() >= limit || current.size() - 1 >= maxHops) {
            return;
        }
        for (Link link : topology.links().values()) {
            if (link.status() != Status.ACTIVE) {
                continue;
            }
            String neighbor;
            if (link.first().equals(currentNode)) {
                neighbor = link.second();
            } else if (link.second().equals(currentNode)) {
                neighbor = link.first();
            } else {
                continue;
            }
            if (topology.nodes().get(neighbor).status() != Status.ACTIVE || !visited.add(neighbor)) {
                continue;
            }
            current.add(neighbor);
            if (neighbor.equals(destination)) {
                paths.add(List.copyOf(current));
            } else {
                findPaths(topology, neighbor, destination, maxHops, limit, visited, current, paths);
            }
            current.remove(current.size() - 1);
            visited.remove(neighbor);
            if (paths.size() >= limit) {
                return;
            }
        }
    }

    private static Set<String> reachableFromControlCenter(Topology topology) {
        Set<String> reachable = new LinkedHashSet<>();
        Node start = topology.nodes().get(CONTROL_CENTER);
        if (start == null || start.status() != Status.ACTIVE) {
            return reachable;
        }
        List<String> pending = new ArrayList<>();
        pending.add(CONTROL_CENTER);
        reachable.add(CONTROL_CENTER);
        for (int index = 0; index < pending.size(); index++) {
            String current = pending.get(index);
            for (Link link : topology.links().values()) {
                if (link.status() != Status.ACTIVE) {
                    continue;
                }
                String neighbor = link.first().equals(current)
                        ? link.second()
                        : link.second().equals(current) ? link.first() : null;
                if (neighbor != null
                        && topology.nodes().get(neighbor).status() == Status.ACTIVE
                        && reachable.add(neighbor)) {
                    pending.add(neighbor);
                }
            }
        }
        return reachable;
    }

    private static void requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank.");
        }
    }
}
