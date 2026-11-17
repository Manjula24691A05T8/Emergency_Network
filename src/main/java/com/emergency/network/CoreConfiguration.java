package com.emergency.network;

import com.emergency.network.core.CrcService;
import com.emergency.network.core.DistanceVectorService;
import com.emergency.network.core.LeakyBucketService;
import com.emergency.network.core.MessageTransferService;
import com.emergency.network.core.NetworkTopology;
import com.emergency.network.core.PacketSimulationService;
import com.emergency.network.core.PerformanceService;
import com.emergency.network.core.ReliableTransmissionService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CoreConfiguration {
    @Bean
    CrcService crcService() {
        return new CrcService();
    }

    @Bean
    DistanceVectorService distanceVectorService() {
        return new DistanceVectorService();
    }

    @Bean
    LeakyBucketService leakyBucketService() {
        return new LeakyBucketService();
    }

    @Bean
    MessageTransferService messageTransferService(PacketSimulationService packetSimulationService) {
        return new MessageTransferService(packetSimulationService);
    }

    @Bean
    NetworkTopology networkTopology() {
        return new NetworkTopology();
    }

    @Bean
    PacketSimulationService packetSimulationService() {
        return new PacketSimulationService();
    }

    @Bean
    PerformanceService performanceService() {
        return new PerformanceService();
    }

    @Bean
    ReliableTransmissionService reliableTransmissionService() {
        return new ReliableTransmissionService();
    }
}
