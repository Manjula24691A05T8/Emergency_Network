# Reliable Emergency Communication Network Under Congested Conditions

## Problem statement

Emergency-service networks need to deliver critical messages reliably even when
traffic is congested or network links and routers fail. This project models those
conditions in a local simulation so routing, error detection, retransmission, and
traffic-shaping behavior can be explored without connecting to real infrastructure.

## Project overview

This Java 17 and Spring Boot application provides a browser-based operations
dashboard backed by Java REST endpoints. It simulates a redundant, ten-node
emergency network and records synthetic packet events in the browser's local
storage. All network behavior is simulated; the application does not contact
emergency services or transmit network traffic.

## Features

- Inspect the network topology and simulate router or link failures.
- Enumerate available paths and compare Dijkstra with Distance Vector routing.
- Preview route changes after a link failure.
- Queue emergency messages by priority, preserving FIFO order within each priority.
- Plan simulated DATA/ACK exchanges and inspect packet events.
- Generate and verify CRC frames, including injected bit errors.
- Simulate Sliding Window and Go-Back-N ARQ, including a dropped packet and retry.
- Model finite-buffer Leaky Bucket congestion on an active router and compare
  normal and reduced-service traffic profiles.
- Review delivery, delay, packet-loss, and modeled-throughput analytics.
- Explore 2D and 3D topology and packet visualizations.

## Technologies

- Java 17
- Spring Boot 3.4.5 and Spring Web
- Maven Wrapper
- JUnit 5, Spring Boot Test, and MockMvc
- HTML, CSS, and JavaScript for the browser dashboard
- Plotly.js 2.35.2 (loaded from its CDN for charts)

The Plotly.js CDN requires an internet connection to render charts. The Java
application and REST API run locally.

## Project structure

```text
.
├── .mvn/wrapper/                 Maven Wrapper configuration
├── src/
│   ├── main/
│   │   ├── java/com/emergency/network/
│   │   │   ├── SimulationController.java
│   │   │   └── core/              Topology, routing, protocol, and analytics services
│   │   └── resources/static/      Dashboard HTML, CSS, and JavaScript
│   └── test/java/com/emergency/network/
│       └── CoreSimulationTests.java
├── mvnw
├── mvnw.cmd
└── pom.xml
```

## Installation

1. Install a Java 17 JDK and ensure `java -version` reports version 17.
2. Clone or download this repository.
3. Open a terminal in the project directory. The Maven Wrapper downloads the
   configured Maven version on its first run; no separate Maven installation is
   required.

## Run the application

On Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

On macOS or Linux:

```sh
./mvnw spring-boot:run
```

Open [http://localhost:8080](http://localhost:8080) in a browser. Stop the
application with `Ctrl+C`.

## Run the tests

On Windows PowerShell:

```powershell
.\mvnw.cmd test
```

On macOS or Linux:

```sh
./mvnw test
```

## Screenshots

No screenshots are included in the repository yet. Add screenshots of the
dashboard and representative simulation views here when they are available.
