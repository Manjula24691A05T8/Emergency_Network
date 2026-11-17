# Emergency Network Operations Center

Java 17 and Spring Boot web application for simulating emergency-network topology,
routing, message delivery, and network protocols. All traffic and failures are
simulated locally; this application does not contact real emergency services or
network devices.

## Run

Install a Java 17 JDK, then run from the project directory. The Maven Wrapper
downloads and uses Maven for you:

```powershell
.\mvnw.cmd spring-boot:run
```

Open [http://localhost:8080](http://localhost:8080).

## Test

```powershell
.\mvnw.cmd test
```

## Features

- Ten-node redundant emergency topology with simulated router/link failures
- Active-path preview, Dijkstra routing, and Distance Vector convergence
- Priority-ordered emergency messages and packet-event monitoring
- CRC generation, bit corruption, and verification with division steps
- Sliding Window and Go-Back-N ARQ simulations
- Leaky Bucket congestion simulation and controlled stress-profile comparison
- Packet delay, delivery, loss, and modeled-throughput analytics
- Interactive 2D topology and 3D network visualization

The simulation services and API are implemented in Java. The browser interface is
served by the Java application from static HTML, CSS, and JavaScript resources.
