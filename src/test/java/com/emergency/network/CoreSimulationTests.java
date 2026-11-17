package com.emergency.network;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.emergency.network.core.CrcService;
import com.emergency.network.core.DistanceVectorService;
import com.emergency.network.core.LeakyBucketService;
import com.emergency.network.core.NetworkTopology;
import com.emergency.network.core.PacketSimulationService;
import com.emergency.network.core.ReliableTransmissionService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CoreSimulationTests {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void crcMatchesKnownDivisionAndDetectsCorruption() {
        CrcService service = new CrcService();
        CrcService.Encoding encoding = service.calculate("1101011011", "10011");

        assertEquals("1110", encoding.remainder());
        assertEquals("11010110111110", encoding.transmittedFrame());
        assertTrue(service.verify(encoding.transmittedFrame(), "10011").valid());
        String corrupted = service.flipBit(encoding.transmittedFrame(), 4);
        assertFalse(service.verify(corrupted, "10011").valid());
    }

    @Test
    void goBackNRetransmitsFromMissingSequenceAndConverges() {
        ReliableTransmissionService service = new ReliableTransmissionService();
        ReliableTransmissionService.GoBackNResult result = service.simulateGoBackN(6, 3, 2);

        assertEquals(List.of(1, 2, 3), result.rounds().get(0).transmitted());
        assertEquals(List.of(1), result.rounds().get(0).received());
        assertEquals(List.of(3), result.rounds().get(0).discarded());
        assertEquals(List.of(2, 3), result.rounds().get(1).transmitted());
        assertEquals(6, result.totalAcknowledged());
        assertEquals(2, result.retransmissionCount());
    }

    @Test
    void slidingWindowAcknowledgesPacketsInBoundedBatches() {
        ReliableTransmissionService.SlidingWindowResult result =
                new ReliableTransmissionService().simulateSlidingWindow(5, 2);

        assertEquals(5, result.totalAcknowledged());
        assertEquals(List.of(1, 2), result.batches().get(0).transmitted());
        assertEquals(List.of(3, 4), result.batches().get(1).acknowledged());
        assertEquals(List.of(5), result.batches().get(2).transmitted());
    }

    @Test
    void leakyBucketReportsFiniteBufferDrops() {
        LeakyBucketService.Result result = new LeakyBucketService().simulate(
                List.of(2, 5, 0),
                3,
                1);

        assertEquals(7, result.totalArrivals());
        assertEquals(4, result.totalAdmitted());
        assertEquals(3, result.totalTransmitted());
        assertEquals(3, result.totalDropped());
        assertEquals("Congested", result.congestionStatus());
    }

    @Test
    void distanceVectorAndPacketSimulationUseAlternateRouteAfterFailure() {
        NetworkTopology topologyService = new NetworkTopology();
        NetworkTopology.Topology topology = topologyService.buildEmergencyTopology(
                List.of(new NetworkTopology.LinkKey("switch_north", "router_a")),
                List.of());
        DistanceVectorService.Result routes = new DistanceVectorService().simulate(topology);
        List<String> route = new DistanceVectorService().path(
                routes,
                "police_station",
                "ambulance_service");
        PacketSimulationService.TransmissionPlan plan =
                new PacketSimulationService().createTransmissionPlan(
                        topology,
                        "police_station",
                        "ambulance_service",
                        "Need medical support.");

        assertTrue(routes.converged());
        assertTrue(route.contains("router_b"));
        assertFalse(route.contains("router_a"));
        assertEquals(route, plan.route());
        assertTrue(plan.estimatedDeliveryDelayMs() > 0);
    }

    @Test
    void controllerServesTopologyAndCrcEndpoints() throws Exception {
        mockMvc.perform(post("/api/topology")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"failedLinks\":[],\"failedNodes\":[]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes.length()").value(10))
                .andExpect(jsonPath("$.metrics.networkHealth").value("Operational"));

        mockMvc.perform(post("/api/crc")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"dataBits":"1101011011","generator":"10011",
                                 "injectError":false,"bitPosition":1}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.encoding.remainder").value("1110"))
                .andExpect(jsonPath("$.verification.valid").value(true));
    }

    @Test
    void controllerRunsRoutingReliableAndCongestionSimulations() throws Exception {
        mockMvc.perform(post("/api/routing")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"source":"police_station","destination":"ambulance_service",
                                 "previewFailure":true,"failedLink":["switch_north","router_a"],
                                 "failedLinks":[],"failedNodes":[]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.dijkstraPath[0]").value("police_station"))
                .andExpect(jsonPath("$.after.dijkstraPath").isArray())
                .andExpect(jsonPath("$.after.dijkstraPath").value(
                        org.hamcrest.Matchers.not(
                                org.hamcrest.Matchers.hasItem("router_a"))));

        mockMvc.perform(post("/api/reliable")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"protocol":"Go-Back-N ARQ","packetCount":6,"windowSize":3,
                                 "lostPacket":2,"source":"police_station",
                                 "destination":"ambulance_service",
                                 "failedLinks":[],"failedNodes":[]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result.totalAcknowledged").value(6))
                .andExpect(jsonPath("$.result.retransmissionCount").value(2));

        mockMvc.perform(post("/api/congestion")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"arrivals":"2,5,0","capacity":3,"outputRate":1,
                                 "router":"router_a","failedLinks":[],"failedNodes":[]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.router").value("router_a"))
                .andExpect(jsonPath("$.result.totalDropped").value(3))
                .andExpect(jsonPath("$.result.congestionStatus").value("Congested"));
    }

    @Test
    void congestionSimulationRejectsFailedRouter() throws Exception {
        mockMvc.perform(post("/api/congestion")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"arrivals":"2,5,0","capacity":3,"outputRate":1,
                                 "router":"router_a","failedLinks":[],
                                 "failedNodes":["router_a"]}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(
                        "Select an active router for congestion simulation."));
    }

    @Test
    void controllerQueuesProcessesAndPlansMessages() throws Exception {
        String queuedMessage = """
                {"queue":[],"sequence":1,"source":"police_station",
                 "destination":"ambulance_service","content":"Need medical support.",
                 "priority":"Critical"}
                """;
        mockMvc.perform(post("/api/messages/queue")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(queuedMessage))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message.messageId").value("MSG-0001"))
                .andExpect(jsonPath("$.queue.length()").value(1));

        mockMvc.perform(post("/api/messages/process")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"queue":[{"messageId":"MSG-0001","sequence":1,
                                 "source":"police_station","destination":"ambulance_service",
                                 "content":"Need medical support.","priority":"Critical",
                                 "queuedAt":"2026-01-01T00:00:00Z"}],
                                 "failedLinks":[],"failedNodes":[]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.queue.length()").value(0))
                .andExpect(jsonPath("$.event.status").value("Delivered"))
                .andExpect(jsonPath("$.event.route.length()").value(5));

        mockMvc.perform(post("/api/packet")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"source":"police_station","destination":"ambulance_service",
                                 "message":"Need medical support.","injectPacketLoss":true,
                                 "failedLinks":[],"failedNodes":[]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.retransmissions").value(1))
                .andExpect(jsonPath("$.route[0]").value("police_station"));
    }

    @Test
    void controllerServesConnectivityAndPerformanceAnalytics() throws Exception {
        mockMvc.perform(post("/api/paths")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"source":"control_center","destination":"ambulance_service",
                                 "failedLinks":[],"failedNodes":[]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths.length()").value(org.hamcrest.Matchers.greaterThanOrEqualTo(2)));

        mockMvc.perform(post("/api/congestion/compare")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"arrivals":"10,0,10","capacity":4,
                                 "normalRate":4,"stressRate":1}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.normal.totalTransmitted").value(8))
                .andExpect(jsonPath("$.stress.totalDropped").value(14));

        mockMvc.perform(post("/api/analytics")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"packetEvents":[{"packetId":"PKT-000001",
                                 "messageId":"MSG-0001","sourceIp":"10.20.0.11",
                                 "destinationIp":"10.20.0.13","protocol":"Emergency DATA/ACK",
                                 "packetSizeBytes":100,"timestamp":"2026-01-01T00:00:00Z",
                                 "status":"Delivered","transmissionDelayMs":2.5,
                                 "priority":"Critical","route":["police_station",
                                 "switch_north","router_a","switch_south",
                                 "ambulance_service"]}]}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalPackets").value(1))
                .andExpect(jsonPath("$.deliveredPackets").value(1))
                .andExpect(jsonPath("$.packetDeliveryRatioPercent").value(100.0));
    }

    @Test
    void invalidCrcRequestReturnsReadableClientError() throws Exception {
        mockMvc.perform(post("/api/crc")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"dataBits":"1102","generator":"10011",
                                 "injectError":false,"bitPosition":1}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").isNotEmpty());

        mockMvc.perform(post("/api/congestion")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"arrivals":"1,,2","capacity":4,"outputRate":1,
                                 "router":"router_a","failedLinks":[],"failedNodes":[]}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").isNotEmpty());
    }
}
