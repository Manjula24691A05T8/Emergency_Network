package com.emergency.network;

import com.emergency.network.core.CrcService;
import com.emergency.network.core.DistanceVectorService;
import com.emergency.network.core.LeakyBucketService;
import com.emergency.network.core.MessageTransferService;
import com.emergency.network.core.NetworkTopology;
import com.emergency.network.core.PacketSimulationService;
import com.emergency.network.core.PerformanceService;
import com.emergency.network.core.ReliableTransmissionService;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class SimulationController {
    private final CrcService crcService;
    private final DistanceVectorService distanceVectorService;
    private final LeakyBucketService leakyBucketService;
    private final MessageTransferService messageTransferService;
    private final NetworkTopology networkTopology;
    private final PacketSimulationService packetSimulationService;
    private final PerformanceService performanceService;
    private final ReliableTransmissionService reliableTransmissionService;

    public SimulationController(
            CrcService crcService,
            DistanceVectorService distanceVectorService,
            LeakyBucketService leakyBucketService,
            MessageTransferService messageTransferService,
            NetworkTopology networkTopology,
            PacketSimulationService packetSimulationService,
            PerformanceService performanceService,
            ReliableTransmissionService reliableTransmissionService) {
        this.crcService = crcService;
        this.distanceVectorService = distanceVectorService;
        this.leakyBucketService = leakyBucketService;
        this.messageTransferService = messageTransferService;
        this.networkTopology = networkTopology;
        this.packetSimulationService = packetSimulationService;
        this.performanceService = performanceService;
        this.reliableTransmissionService = reliableTransmissionService;
    }

    @PostMapping("/topology")
    public TopologyView topology(@RequestBody TopologyRequest request) {
        NetworkTopology.Topology topology = buildTopology(request.failedLinks(), request.failedNodes());
        List<NodeView> nodes = topology.nodes().values().stream()
                .map(node -> new NodeView(
                        node.id(),
                        node.label(),
                        node.shortLabel(),
                        node.kind(),
                        node.role(),
                        node.address(),
                        node.x(),
                        node.y(),
                        node.status().name().toLowerCase()))
                .toList();
        List<LinkView> links = topology.links().values().stream()
                .map(link -> new LinkView(
                        link.first(),
                        link.second(),
                        link.bandwidthMbps(),
                        link.delayMs(),
                        link.status().name().toLowerCase()))
                .toList();
        return new TopologyView(nodes, links, networkTopology.metrics(topology));
    }

    @PostMapping("/paths")
    public PathsResponse paths(@RequestBody PathsRequest request) {
        NetworkTopology.Topology topology = buildTopology(request.failedLinks(), request.failedNodes());
        return new PathsResponse(networkTopology.availablePaths(
                topology,
                request.source(),
                request.destination()));
    }

    @PostMapping("/routing")
    public RoutingResponse routing(@RequestBody RoutingRequest request) {
        if (request.source().equals(request.destination())) {
            throw new IllegalArgumentException("Choose different source and destination services.");
        }
        NetworkTopology.Topology before = buildTopology(request.failedLinks(), request.failedNodes());
        RoutingResult current = calculateRoutes(before, request.source(), request.destination());
        RoutingResult after = null;
        if (request.previewFailure()) {
            if (request.failedLink() == null || request.failedLink().size() != 2) {
                throw new IllegalArgumentException("Select a link to remove in the failure preview.");
            }
            List<NetworkTopology.LinkKey> failedLinks = new ArrayList<>(
                    request.failedLinks().stream()
                            .map(pair -> new NetworkTopology.LinkKey(pair.get(0), pair.get(1)))
                            .toList());
            failedLinks.add(new NetworkTopology.LinkKey(
                    request.failedLink().get(0),
                    request.failedLink().get(1)));
            NetworkTopology.Topology preview = networkTopology.buildEmergencyTopology(
                    failedLinks,
                    request.failedNodes());
            after = calculateRoutes(preview, request.source(), request.destination());
        }
        return new RoutingResponse(
                current.dijkstraPath(),
                current.dijkstraCost(),
                current.distanceVectorPath(),
                current.distanceVectorCost(),
                current.convergenceRound(),
                current.convergenceHistory(),
                after);
    }

    @PostMapping("/crc")
    public CrcResponse crc(@RequestBody CrcRequest request) {
        if (request.dataBits().length() > 256) {
            throw new IllegalArgumentException("Data must contain no more than 256 bits.");
        }
        if (request.generator().length() > 32) {
            throw new IllegalArgumentException("Generator polynomial must contain no more than 32 bits.");
        }
        CrcService.Encoding encoding = crcService.calculate(request.dataBits(), request.generator());
        String receivedFrame = request.injectError()
                ? crcService.flipBit(encoding.transmittedFrame(), request.bitPosition())
                : encoding.transmittedFrame();
        CrcService.Verification verification = crcService.verify(receivedFrame, encoding.generator());
        return new CrcResponse(encoding, verification);
    }

    @PostMapping("/reliable")
    public ReliableResponse reliable(@RequestBody ReliableRequest request) {
        if (request.source().equals(request.destination())) {
            throw new IllegalArgumentException("Choose different sender and receiver services.");
        }
        NetworkTopology.Topology topology = buildTopology(request.failedLinks(), request.failedNodes());
        PacketSimulationService.TransmissionPlan plan = packetSimulationService.createTransmissionPlan(
                topology,
                request.source(),
                request.destination(),
                "Reliable data frame");

        ReliableResultView result;
        if ("Sliding Window".equals(request.protocol())) {
            if (request.lostPacket() != null) {
                throw new IllegalArgumentException("Packet loss injection is available only for Go-Back-N ARQ.");
            }
            ReliableTransmissionService.SlidingWindowResult slidingWindow =
                    reliableTransmissionService.simulateSlidingWindow(
                    request.packetCount(),
                    request.windowSize());
            result = new ReliableResultView(
                    slidingWindow.packetCount(),
                    slidingWindow.windowSize(),
                    null,
                    slidingWindow.totalAcknowledged(),
                    0,
                    0,
                    List.of(),
                    slidingWindow.batches());
        } else if ("Go-Back-N ARQ".equals(request.protocol())) {
            ReliableTransmissionService.GoBackNResult goBackN =
                    reliableTransmissionService.simulateGoBackN(
                    request.packetCount(),
                    request.windowSize(),
                    request.lostPacket());
            result = new ReliableResultView(
                    goBackN.packetCount(),
                    goBackN.windowSize(),
                    goBackN.lostPacket(),
                    goBackN.totalAcknowledged(),
                    goBackN.retransmissionCount(),
                    goBackN.timeoutCount(),
                    goBackN.rounds(),
                    List.of());
        } else {
            throw new IllegalArgumentException("Choose a supported reliable-transmission protocol.");
        }
        return new ReliableResponse(result, plan.route(), plan.estimatedDeliveryDelayMs());
    }

    @PostMapping("/congestion")
    public CongestionResponse congestion(@RequestBody CongestionRequest request) {
        NetworkTopology.Topology topology = buildTopology(request.failedLinks(), request.failedNodes());
        NetworkTopology.Node router = topology.node(request.router());
        if (router == null || !NetworkTopology.ROUTER_NODES.contains(router.id())
                || router.status() != NetworkTopology.Status.ACTIVE) {
            throw new IllegalArgumentException("Select an active router for congestion simulation.");
        }
        LeakyBucketService.Result result = leakyBucketService.simulate(
                leakyBucketService.parseArrivals(request.arrivals()),
                request.capacity(),
                request.outputRate());
        return new CongestionResponse(toView(result), router.id());
    }

    @PostMapping("/congestion/compare")
    public ProfileResponse compareCongestion(@RequestBody ProfileRequest request) {
        LeakyBucketService.ProfileComparison comparison = leakyBucketService.compareProfiles(
                leakyBucketService.parseArrivals(request.arrivals()),
                request.capacity(),
                request.normalRate(),
                request.stressRate());
        return new ProfileResponse(toView(comparison.normal()), toView(comparison.stress()));
    }

    @PostMapping("/packet")
    public PacketSimulationService.TransmissionPlan packet(@RequestBody PacketRequest request) {
        return packetSimulationService.createTransmissionPlan(
                buildTopology(request.failedLinks(), request.failedNodes()),
                request.source(),
                request.destination(),
                request.message(),
                request.injectPacketLoss());
    }

    @PostMapping("/messages/queue")
    public QueueResponse queueMessage(@RequestBody QueueRequest request) {
        int nextSequence = request.sequence();
        MessageTransferService.EmergencyMessage message = new MessageTransferService.EmergencyMessage(
                "MSG-%04d".formatted(nextSequence),
                nextSequence,
                request.source(),
                request.destination(),
                request.content(),
                request.priority(),
                OffsetDateTime.now().toString());
        List<MessageTransferService.EmergencyMessage> queue =
                messageTransferService.enqueue(request.queue(), message);
        return new QueueResponse(queue, message);
    }

    @PostMapping("/messages/process")
    public ProcessResponse processMessage(@RequestBody ProcessRequest request) {
        List<MessageTransferService.EmergencyMessage> ordered =
                messageTransferService.orderMessages(request.queue());
        if (ordered.isEmpty()) {
            throw new IllegalArgumentException("The emergency-message queue is empty.");
        }
        MessageTransferService.EmergencyMessage message = ordered.get(0);
        NetworkTopology.Topology topology = buildTopology(request.failedLinks(), request.failedNodes());
        MessageTransferService.PacketEvent event =
                messageTransferService.processMessage(topology, message);
        return new ProcessResponse(ordered.subList(1, ordered.size()), event);
    }

    @PostMapping("/analytics")
    public PerformanceService.Summary analytics(@RequestBody AnalyticsRequest request) {
        return performanceService.summarize(request.packetEvents());
    }

    private NetworkTopology.Topology buildTopology(
            List<List<String>> failedLinks,
            List<String> failedNodes) {
        return networkTopology.buildEmergencyTopology(toLinkKeys(failedLinks), failedNodes);
    }

    private static LeakyBucketResultView toView(LeakyBucketService.Result result) {
        return new LeakyBucketResultView(
                result.capacity(),
                result.outputRate(),
                result.steps(),
                result.totalArrivals(),
                result.totalAdmitted(),
                result.totalTransmitted(),
                result.totalDropped(),
                result.peakOccupancy(),
                result.congestedSlots(),
                result.congestionRatePercent(),
                result.congestionStatus());
    }

    private static List<NetworkTopology.LinkKey> toLinkKeys(List<List<String>> pairs) {
        if (pairs == null) {
            return List.of();
        }
        return pairs.stream().map(pair -> {
            if (pair == null || pair.size() != 2) {
                throw new IllegalArgumentException("Each failed link must identify two endpoints.");
            }
            return new NetworkTopology.LinkKey(pair.get(0), pair.get(1));
        }).toList();
    }

    private RoutingResult calculateRoutes(
            NetworkTopology.Topology topology,
            String source,
            String destination) {
        DistanceVectorService.Result distanceVector = distanceVectorService.simulate(topology);
        List<String> dijkstraPath = shortestPath(topology, source, destination);
        List<String> distanceVectorPath =
                distanceVector.tables().containsKey(source)
                        ? distanceVectorService.path(distanceVector, source, destination)
                        : List.of();
        Double dijkstraCost = pathCost(topology, dijkstraPath);
        Double distanceVectorCost = pathCost(topology, distanceVectorPath);
        List<ConvergencePoint> history = distanceVector.history().stream()
                .map(snapshot -> {
                    DistanceVectorService.RouteEntry entry = snapshot.tables()
                            .getOrDefault(source, Map.of())
                            .get(destination);
                    return new ConvergencePoint(
                            snapshot.roundNumber(),
                            entry == null ? null : entry.cost());
                })
                .toList();
        return new RoutingResult(
                dijkstraPath,
                dijkstraCost,
                distanceVectorPath,
                distanceVectorCost,
                distanceVector.convergenceRound(),
                history);
    }

    private static List<String> shortestPath(
            NetworkTopology.Topology topology,
            String source,
            String destination) {
        if (!topology.nodes().containsKey(source) || !topology.nodes().containsKey(destination)) {
            throw new IllegalArgumentException("Source and destination must be nodes in the topology.");
        }
        if (topology.node(source).status() != NetworkTopology.Status.ACTIVE
                || topology.node(destination).status() != NetworkTopology.Status.ACTIVE) {
            return List.of();
        }
        Map<String, Double> distances = new HashMap<>();
        Map<String, String> previous = new HashMap<>();
        PriorityQueue<QueueEntry> queue = new PriorityQueue<>(Comparator.comparingDouble(QueueEntry::cost));
        distances.put(source, 0.0);
        queue.add(new QueueEntry(source, 0.0));

        while (!queue.isEmpty()) {
            QueueEntry current = queue.remove();
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
                String neighbor = link.first().equals(current.node())
                        ? link.second()
                        : link.second().equals(current.node()) ? link.first() : null;
                if (neighbor == null
                        || topology.node(neighbor).status() != NetworkTopology.Status.ACTIVE) {
                    continue;
                }
                double candidate = current.cost() + link.delayMs();
                if (candidate < distances.getOrDefault(neighbor, Double.POSITIVE_INFINITY)) {
                    distances.put(neighbor, candidate);
                    previous.put(neighbor, current.node());
                    queue.add(new QueueEntry(neighbor, candidate));
                }
            }
        }
        if (!distances.containsKey(destination)) {
            return List.of();
        }
        List<String> path = new ArrayList<>();
        String current = destination;
        while (current != null) {
            path.add(current);
            if (current.equals(source)) {
                break;
            }
            current = previous.get(current);
        }
        if (!path.get(path.size() - 1).equals(source)) {
            return List.of();
        }
        java.util.Collections.reverse(path);
        return List.copyOf(path);
    }

    private static Double pathCost(NetworkTopology.Topology topology, List<String> path) {
        if (path.isEmpty()) {
            return null;
        }
        double cost = 0;
        for (int index = 1; index < path.size(); index++) {
            NetworkTopology.Link link = topology.link(path.get(index - 1), path.get(index));
            if (link == null || link.status() != NetworkTopology.Status.ACTIVE) {
                return null;
            }
            cost += link.delayMs();
        }
        return cost;
    }

    public record TopologyRequest(List<List<String>> failedLinks, List<String> failedNodes) {}

    public record PathsRequest(
            String source,
            String destination,
            List<List<String>> failedLinks,
            List<String> failedNodes) {}

    public record RoutingRequest(
            String source,
            String destination,
            boolean previewFailure,
            List<String> failedLink,
            List<List<String>> failedLinks,
            List<String> failedNodes) {}

    public record CrcRequest(String dataBits, String generator, boolean injectError, int bitPosition) {}

    public record ReliableRequest(
            String protocol,
            int packetCount,
            int windowSize,
            Integer lostPacket,
            String source,
            String destination,
            List<List<String>> failedLinks,
            List<String> failedNodes) {}

    public record CongestionRequest(
            String arrivals,
            int capacity,
            int outputRate,
            String router,
            List<List<String>> failedLinks,
            List<String> failedNodes) {}

    public record ProfileRequest(String arrivals, int capacity, int normalRate, int stressRate) {}

    public record PacketRequest(
            String source,
            String destination,
            String message,
            boolean injectPacketLoss,
            List<List<String>> failedLinks,
            List<String> failedNodes) {}

    public record QueueRequest(
            List<MessageTransferService.EmergencyMessage> queue,
            int sequence,
            String source,
            String destination,
            String content,
            String priority) {}

    public record ProcessRequest(
            List<MessageTransferService.EmergencyMessage> queue,
            List<List<String>> failedLinks,
            List<String> failedNodes) {}

    public record AnalyticsRequest(List<MessageTransferService.PacketEvent> packetEvents) {}

    public record NodeView(
            String id,
            String label,
            String shortLabel,
            String kind,
            String role,
            String address,
            double x,
            double y,
            String status) {}

    public record LinkView(
            String source,
            String target,
            int bandwidthMbps,
            double delayMs,
            String status) {}

    public record TopologyView(
            List<NodeView> nodes,
            List<LinkView> links,
            NetworkTopology.TopologyMetrics metrics) {}

    public record PathsResponse(List<List<String>> paths) {}

    public record ConvergencePoint(int round, Double cost) {}

    public record RoutingResult(
            List<String> dijkstraPath,
            Double dijkstraCost,
            List<String> distanceVectorPath,
            Double distanceVectorCost,
            int convergenceRound,
            List<ConvergencePoint> convergenceHistory) {}

    public record RoutingResponse(
            List<String> dijkstraPath,
            Double dijkstraCost,
            List<String> distanceVectorPath,
            Double distanceVectorCost,
            int convergenceRound,
            List<ConvergencePoint> convergenceHistory,
            RoutingResult after) {}

    public record CrcResponse(CrcService.Encoding encoding, CrcService.Verification verification) {}

    public record ReliableResultView(
            int packetCount,
            int windowSize,
            Integer lostPacket,
            int totalAcknowledged,
            int retransmissionCount,
            int timeoutCount,
            List<ReliableTransmissionService.GoBackNRound> rounds,
            List<ReliableTransmissionService.SlidingWindowBatch> batches) {}

    public record ReliableResponse(
            ReliableResultView result,
            List<String> route,
            double estimatedDeliveryDelayMs) {}

    public record LeakyBucketResultView(
            int capacity,
            int outputRate,
            List<LeakyBucketService.Step> steps,
            long totalArrivals,
            long totalAdmitted,
            long totalTransmitted,
            long totalDropped,
            int peakOccupancy,
            int congestedSlots,
            double congestionRatePercent,
            String congestionStatus) {}

    public record CongestionResponse(LeakyBucketResultView result, String router) {}

    public record ProfileResponse(
            LeakyBucketResultView normal,
            LeakyBucketResultView stress) {}

    public record QueueResponse(
            List<MessageTransferService.EmergencyMessage> queue,
            MessageTransferService.EmergencyMessage message) {}

    public record ProcessResponse(
            List<MessageTransferService.EmergencyMessage> queue,
            MessageTransferService.PacketEvent event) {}

    private record QueueEntry(String node, double cost) {}
}
