const pages = ["dashboard", "topology", "routing", "communication", "crc", "reliable", "congestion", "monitor", "analytics", "infrastructure"];
const state = {
    failedLinks: load("failedLinks", []),
    failedNodes: load("failedNodes", []),
    messages: load("messages", []),
    packetEvents: load("packetEvents", []),
    activity: load("activity", []),
    messageSequence: load("messageSequence", 0),
    latestBucket: load("latestBucket", null),
    latestReliable: null,
    lastPacketPlan: null,
    lastPacketRequest: null,
    topology: null
};

function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(`enoc.${key}`)) ?? fallback; }
    catch { return fallback; }
}

function save(key, value) {
    localStorage.setItem(`enoc.${key}`, JSON.stringify(value));
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
}

function showNotice(message, isError = false) {
    const notice = document.getElementById("notice");
    notice.textContent = message;
    notice.hidden = false;
    notice.style.borderColor = isError ? "#82434a" : "#2a7158";
    notice.style.background = isError ? "#3a2025" : "#143427";
    window.setTimeout(() => { notice.hidden = true; }, 5000);
}

async function api(url, body) {
    const response = await fetch(url, {
        method: body === undefined ? "GET" : "POST",
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || data.error || `Request failed (${response.status})`);
    return data;
}

function linkKey(first, second) {
    return [first, second].sort().join("|");
}

function addActivity(text) {
    state.activity.unshift(`${new Date().toLocaleTimeString()} · ${text}`);
    state.activity = state.activity.slice(0, 10);
    save("activity", state.activity);
    renderActivity();
}

function getNode(id) {
    return state.topology?.nodes?.find(node => node.id === id);
}

function label(id, short = false) {
    const node = getNode(id);
    return node ? (short ? node.shortLabel : node.label) : id;
}

function metricCards(target, entries) {
    document.getElementById(target).innerHTML = entries.map(([name, value]) =>
        `<div class="metric"><span class="metric-label">${escapeHtml(name)}</span><strong class="metric-value">${escapeHtml(value)}</strong></div>`
    ).join("");
}

function fillSelect(id, items, selected) {
    const element = document.getElementById(id);
    if (!element) return;
    const previous = selected ?? element.value;
    element.innerHTML = items.map(item => {
        const value = typeof item === "string" ? item : item.id;
        const text = typeof item === "string" ? label(item) : item.label;
        return `<option value="${escapeHtml(value)}">${escapeHtml(text)}</option>`;
    }).join("");
    if (items.some(item => (typeof item === "string" ? item : item.id) === previous)) element.value = previous;
}

function topologyMetrics(metrics) {
    return [
        ["Network nodes", metrics.totalNodes ?? 0],
        ["Active routers", metrics.activeRouters ?? 0],
        ["Active switches", metrics.activeSwitches ?? 0],
        ["Active links", metrics.activeConnections ?? 0],
        ["Failed links", metrics.failedConnections ?? 0],
        ["Reachable services", `${metrics.reachableServices ?? 0}/${metrics.totalServices ?? 0}`],
        ["Network health", metrics.networkHealth ?? "Unknown"]
    ];
}

function renderNetworkChart(containerId, threeDimensional = false) {
    const container = document.getElementById(containerId);
    const topology = state.topology;
    if (!container || !topology) return;
    if (typeof Plotly === "undefined") {
        container.innerHTML = `<p class="empty-state">Visualization library is unavailable. The network inventory remains available below.</p>`;
        return;
    }

    const links = topology.links || [];
    const traces = [];
    for (const failed of [false, true]) {
        const selected = links.filter(link => (link.status === "failed") === failed);
        const x = [], y = [], z = [];
        for (const edge of selected) {
            const first = getNode(edge.source), second = getNode(edge.target);
            if (!first || !second) continue;
            x.push(first.x, second.x, null);
            y.push(first.y, second.y, null);
            z.push(first.z ?? 0, second.z ?? 0, null);
        }
        traces.push({
            type: threeDimensional ? "scatter3d" : "scatter",
            mode: "lines",
            x, y,
            ...(threeDimensional ? { z } : {}),
            name: failed ? "Failed link" : "Active link",
            line: { color: failed ? "#e06d70" : "#287da5", width: failed ? 3 : 2, dash: failed ? "dash" : "solid" },
            hoverinfo: "skip"
        });
    }

    const nodeTrace = {
        type: threeDimensional ? "scatter3d" : "scatter",
        mode: "markers+text",
        x: topology.nodes.map(node => node.x),
        y: topology.nodes.map(node => node.y),
        ...(threeDimensional ? { z: topology.nodes.map(node => node.z ?? (node.kind === "router" ? 1.1 : 0.1)) } : {}),
        text: topology.nodes.map(node => node.shortLabel),
        textposition: threeDimensional ? undefined : "bottom center",
        textfont: { color: "#dce8f1", size: 10 },
        customdata: topology.nodes.map(node => [node.label, node.role, node.address, node.status]),
        hovertemplate: "<b>%{customdata[0]}</b><br>Role: %{customdata[1]}<br>IP: %{customdata[2]}<br>Status: %{customdata[3]}<extra></extra>",
        marker: {
            size: threeDimensional ? 8 : 20,
            color: topology.nodes.map(node => node.status === "failed" ? "#e06d70" : ({ service: "#38b9d8", router: "#4c8bf5", switch: "#41d39b" }[node.kind] || "#9aafc1")),
            symbol: topology.nodes.map(node => node.kind === "router" ? "diamond" : node.kind === "switch" ? "square" : "circle"),
            line: { color: "#dce8f1", width: 1 }
        },
        name: "Network devices"
    };
    traces.push(nodeTrace);
    const activeLinkKeys = new Set(links.filter(link => link.status === "active")
        .map(link => linkKey(link.source, link.target)));
    const packetRoute = state.lastPacketPlan?.route || [];
    const packetRouteIsActive = packetRoute.length > 1 && packetRoute.slice(1).every((node, index) =>
        activeLinkKeys.has(linkKey(packetRoute[index], node)));
    if (threeDimensional && packetRouteIsActive) {
        const routeNodes = packetRoute.map(getNode);
        traces.push({
            type: "scatter3d",
            mode: "lines",
            x: routeNodes.map(node => node.x),
            y: routeNodes.map(node => node.y),
            z: routeNodes.map(node => node.z ?? (node.kind === "router" ? 1.1 : 0.1)),
            name: "Selected packet route",
            line: { color: "#55c79a", width: 7 }
        });
    }
    if (threeDimensional && state.latestBucket?.result?.steps?.length) {
        const router = getNode(state.latestBucket.router);
        const tick = Math.max(1, Math.min(
            state.latestBucket.selectedTick || 1,
            state.latestBucket.result.steps.length
        ));
        const step = state.latestBucket.result.steps[tick - 1];
        if (router && step) {
            traces.push({
                type: "scatter3d",
                mode: "markers+text",
                x: [router.x],
                y: [router.y],
                z: [(router.z ?? 1.1) + 0.25],
                text: [`Queue ${step.queuedBeforeLeak}/${state.latestBucket.result.capacity}`],
                textposition: "top center",
                name: "Router queue",
                marker: {
                    size: 12 + Math.min(step.queuedBeforeLeak, state.latestBucket.result.capacity) * 1.5,
                    color: step.dropped > 0 ? "#e06d70" : "#e8a653"
                },
                hovertemplate: `Slot ${step.tick}<br>Queued: ${step.queuedBeforeLeak}/${state.latestBucket.result.capacity}<br>Transmitted: ${step.transmitted}<br>Dropped: ${step.dropped}<extra></extra>`
            });
        }
    }
    const layout = {
        height: threeDimensional ? 550 : 430,
        margin: { l: 15, r: 15, t: 18, b: 25 },
        paper_bgcolor: "#0c1928",
        plot_bgcolor: "#0c1928",
        font: { color: "#dce8f1", family: "Inter, Segoe UI, sans-serif" },
        legend: { orientation: "h", x: 0.02, y: 1.06 },
        ...(threeDimensional ? {
            scene: {
                bgcolor: "#0c1928",
                xaxis: { visible: false },
                yaxis: { visible: false },
                zaxis: { visible: false },
                camera: { eye: { x: 1.6, y: 1.5, z: 1.1 } }
            }
        } : {
            xaxis: { visible: false, range: [-4, 4], fixedrange: false },
            yaxis: { visible: false, range: [-1.6, 2.2], scaleanchor: "x", scaleratio: 1, fixedrange: false },
            dragmode: "pan"
        })
    };
    Plotly.react(container, traces, layout, { displaylogo: false, responsive: true, scrollZoom: true });
}

function renderTopology() {
    const topology = state.topology;
    if (!topology) return;
    metricCards("topology-metrics", topologyMetrics(topology.metrics));
    metricCards("dashboard-metrics", [
        ["Network nodes", topology.metrics.totalNodes],
        ["Active links", topology.metrics.activeConnections],
        ["Network health", topology.metrics.networkHealth],
        ["Messages processed", state.packetEvents.length],
        ["Congestion", state.latestBucket?.result?.congestionStatus || "Not run"],
        ["Throughput", "No packet data"]
    ]);

    const allNodes = topology.nodes.map(node => ({ id: node.id, label: node.label }));
    const services = topology.nodes.filter(node => node.kind === "service").map(node => ({ id: node.id, label: node.label }));
    const routers = topology.nodes.filter(node => node.kind === "router").map(node => ({ id: node.id, label: node.label }));
    const edgeOptions = topology.links.map(edge => ({ id: linkKey(edge.source, edge.target), label: `${label(edge.source)} ↔ ${label(edge.target)}` }));

    fillSelect("topology-link", edgeOptions);
    fillSelect("topology-router", routers);
    fillSelect("path-source", services, "control_center");
    fillSelect("path-destination", services, "ambulance_service");
    fillSelect("routing-source", services, "police_station");
    fillSelect("routing-destination", services, "ambulance_service");
    fillSelect("routing-failure-link", edgeOptions);
    fillSelect("message-source", services, "police_station");
    fillSelect("message-destination", services, "ambulance_service");
    fillSelect("reliable-source", services, "police_station");
    fillSelect("reliable-destination", services, "ambulance_service");
    fillSelect("congestion-router", routers.filter(router => getNode(router.id)?.status === "active"));
    fillSelect("packet-source", allNodes, "police_station");
    fillSelect("packet-destination", allNodes, "ambulance_service");

    const selectedLink = document.getElementById("topology-link")?.value;
    const selectedEdge = topology.links.find(edge => linkKey(edge.source, edge.target) === selectedLink);
    document.getElementById("fail-link").disabled = !selectedEdge || selectedEdge.status === "failed";
    document.getElementById("restore-link").disabled = !selectedEdge || selectedEdge.status === "active" || state.failedNodes.some(node => [selectedEdge.source, selectedEdge.target].includes(node));
    const selectedRouter = document.getElementById("topology-router")?.value;
    document.getElementById("fail-router").disabled = !selectedRouter || getNode(selectedRouter)?.status === "failed";
    document.getElementById("restore-router").disabled = !selectedRouter || getNode(selectedRouter)?.status !== "failed";
    document.getElementById("restore-all").disabled = !state.failedLinks.length && !state.failedNodes.length;

    renderNetworkChart("topology-chart");
    renderNetworkChart("dashboard-topology");
    document.getElementById("link-inventory").innerHTML = `<table><thead><tr><th>Connection</th><th>Status</th><th>Bandwidth</th><th>Delay</th></tr></thead><tbody>${topology.links.map(edge =>
        `<tr><td>${escapeHtml(label(edge.source))} ↔ ${escapeHtml(label(edge.target))}</td><td>${escapeHtml(edge.status.toUpperCase())}</td><td>${escapeHtml(edge.bandwidthMbps)} Mbps</td><td>${escapeHtml(edge.delayMs)} ms</td></tr>`
    ).join("")}</tbody></table>`;
    renderActivity();
    renderQueue();
    renderMonitor();
    renderAnalytics().catch(error => showNotice(error.message, true));
}

async function refreshTopology() {
    state.topology = await api("/api/topology", { failedLinks: state.failedLinks, failedNodes: state.failedNodes });
    renderTopology();
    if (state.lastPacketRequest) {
        const previousRoute = state.lastPacketPlan?.route || [];
        try {
            state.lastPacketPlan = await api("/api/packet", {
                ...state.lastPacketRequest,
                failedLinks: state.failedLinks,
                failedNodes: state.failedNodes
            });
            const nextRoute = state.lastPacketPlan.route || [];
            showResult("packet-result", `<h2>Route recovery</h2><p><strong>Before:</strong> ${previousRoute.map(node => escapeHtml(label(node, true))).join(" → ") || "Unavailable"}</p><p><strong>After:</strong> ${nextRoute.map(node => escapeHtml(label(node, true))).join(" → ")}</p><p>DATA/ACK exchange recalculated over active links.</p>`, "success");
        } catch (error) {
            state.lastPacketPlan = null;
            showResult("packet-result", `<strong>No active route reaches the prepared destination.</strong><p>${escapeHtml(error.message)}</p>`, "warning");
        }
        renderNetworkChart("infrastructure-chart", true);
    }
}

function renderActivity() {
    const target = document.getElementById("activity-list");
    if (target) target.innerHTML = state.activity.length ? state.activity.map(item => `<p>${escapeHtml(item)}</p>`).join("") : "No simulated activity yet.";
}

function renderQueueSnapshot() {
    const result = state.latestBucket?.result;
    const slider = document.getElementById("bucket-tick");
    if (!result?.steps?.length || !slider) return;
    const tick = Math.max(1, Math.min(Number(slider.value), result.steps.length));
    slider.value = String(tick);
    state.latestBucket.selectedTick = tick;
    save("latestBucket", state.latestBucket);
    const step = result.steps[tick - 1];
    document.getElementById("bucket-slot-value").textContent = `Slot ${tick}`;
    document.getElementById("queue-snapshot").innerHTML =
        `<p><strong>${escapeHtml(label(state.latestBucket.router, true))}</strong> · Queue ${step.queuedBeforeLeak}/${result.capacity} · Incoming ${step.arrivals} · Transmitted ${step.transmitted} · Dropped ${step.dropped} · Remaining ${step.queuedAfterLeak}</p>`;
    renderNetworkChart("infrastructure-chart", true);
}

function showResult(id, content, status = "") {
    const target = document.getElementById(id);
    if (target) target.innerHTML = `<div class="result-card ${status}">${content}</div>`;
}

function displayError(id, error) {
    showResult(id, `<strong>Simulation not run.</strong><p>${escapeHtml(error.message)}</p>`, "error");
}

function renderQueue() {
    const target = document.getElementById("message-queue");
    if (!target) return;
    if (!state.messages.length) {
        target.innerHTML = `<p class="empty-state">The priority queue is empty.</p>`;
        document.getElementById("process-message").disabled = true;
        return;
    }
    document.getElementById("process-message").disabled = false;
    target.innerHTML = `<table><thead><tr><th>ID</th><th>Priority</th><th>Sender → receiver</th><th>Message</th></tr></thead><tbody>${state.messages.map(item =>
        `<tr><td>${escapeHtml(item.messageId)}</td><td>${escapeHtml(item.priority)}</td><td>${escapeHtml(label(item.source, true))} → ${escapeHtml(label(item.destination, true))}</td><td>${escapeHtml(item.content)}</td></tr>`
    ).join("")}</tbody></table>`;
}

function renderMonitor() {
    const target = document.getElementById("monitor-result");
    if (!target) return;
    const status = document.getElementById("monitor-status")?.value || "All";
    const priority = document.getElementById("monitor-priority")?.value || "All";
    const filtered = state.packetEvents.filter(event =>
        (status === "All" || (status === "Failed" ? event.status.startsWith("Failed") : event.status === status)) &&
        (priority === "All" || event.priority === priority)
    );
    const delivered = state.packetEvents.filter(event => event.status === "Delivered").length;
    target.innerHTML = `<div class="metric-grid"><div class="metric"><span class="metric-label">Recorded packets</span><strong class="metric-value">${state.packetEvents.length}</strong></div><div class="metric"><span class="metric-label">Delivered</span><strong class="metric-value">${delivered}</strong></div><div class="metric"><span class="metric-label">Failed</span><strong class="metric-value">${state.packetEvents.length - delivered}</strong></div></div>` +
        (filtered.length ? `<table><thead><tr><th>Packet</th><th>Source IP</th><th>Destination IP</th><th>Bytes</th><th>Status</th><th>Delay</th></tr></thead><tbody>${filtered.map(event =>
            `<tr><td>${escapeHtml(event.packetId)}</td><td>${escapeHtml(event.sourceIp)}</td><td>${escapeHtml(event.destinationIp)}</td><td>${escapeHtml(event.packetSizeBytes)}</td><td>${escapeHtml(event.status)}</td><td>${event.transmissionDelayMs == null ? "Not available" : `${Number(event.transmissionDelayMs).toFixed(2)} ms`}</td></tr>`
        ).join("")}</tbody></table>` : `<p class="empty-state">${state.packetEvents.length ? "No packets match the selected filters." : "No packets recorded. Queue and process a message first."}</p>`);
}

async function renderAnalytics() {
    const summary = await api("/api/analytics", { packetEvents: state.packetEvents });
    metricCards("analytics-metrics", [
        ["Packets", summary.totalPackets ?? 0],
        ["Delivered", summary.deliveredPackets ?? 0],
        ["Delivery ratio", summary.packetDeliveryRatioPercent == null ? "No packet data" : `${Number(summary.packetDeliveryRatioPercent).toFixed(1)}%`],
        ["Average delay", summary.averageDelayMs == null ? "No delivered packets" : `${Number(summary.averageDelayMs).toFixed(2)} ms`],
        ["Modeled throughput", summary.modeledThroughputMbps == null ? "No packet data" : `${Number(summary.modeledThroughputMbps).toFixed(4)} Mbps`]
    ]);
    if (state.topology) {
        metricCards("dashboard-metrics", [
            ["Network nodes", state.topology.metrics.totalNodes],
            ["Active links", state.topology.metrics.activeConnections],
            ["Network health", state.topology.metrics.networkHealth],
            ["Messages processed", summary.totalPackets],
            ["Messages delivered", summary.deliveredPackets],
            ["Message loss", summary.packetLossRatioPercent == null ? "No packet data" : `${Number(summary.packetLossRatioPercent).toFixed(1)}%`],
            ["Average message delay", summary.averageDelayMs == null ? "No delivered packets" : `${Number(summary.averageDelayMs).toFixed(2)} ms`],
            ["Throughput", summary.modeledThroughputMbps == null ? "No packet data" : `${Number(summary.modeledThroughputMbps).toFixed(4)} Mbps`],
            ["Congestion", state.latestBucket?.result?.congestionStatus || "Not run"]
        ]);
    }
    const container = document.getElementById("analytics-chart");
    if (!container || typeof Plotly === "undefined") return;
    const events = state.packetEvents;
    Plotly.react(container, [
        { type: "bar", x: ["Delivered", "Failed"], y: [summary.deliveredPackets || 0, summary.failedPackets || 0], marker: { color: ["#55c79a", "#e06d70"] }, name: "Packet outcomes" },
        { type: "scatter", x: events.filter(event => event.transmissionDelayMs != null).map(event => event.packetId), y: events.filter(event => event.transmissionDelayMs != null).map(event => event.transmissionDelayMs), mode: "lines+markers", yaxis: "y2", line: { color: "#36c5e8" }, name: "Estimated DATA/ACK delay" }
    ], { height: 360, paper_bgcolor: "#0c1928", plot_bgcolor: "#0c1928", font: { color: "#dce8f1" }, yaxis: { title: "Packets", gridcolor: "#24394b" }, yaxis2: { title: "Delay (ms)", overlaying: "y", side: "right" }, legend: { orientation: "h" }, margin: { t: 25, b: 35, l: 45, r: 45 } }, { responsive: true, displaylogo: false });
}

function setPage(name) {
    for (const page of pages) document.getElementById(`page-${page}`).classList.toggle("active", page === name);
    document.querySelectorAll(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.page === name));
    if (name === "monitor") renderMonitor();
    if (name === "analytics") renderAnalytics().catch(error => showNotice(error.message, true));
    if (name === "infrastructure") renderNetworkChart("infrastructure-chart", true);
}

for (const button of document.querySelectorAll(".nav-item")) button.addEventListener("click", () => setPage(button.dataset.page));
for (const button of document.querySelectorAll("[data-go]")) button.addEventListener("click", () => setPage(button.dataset.go));
document.getElementById("reduced-motion").checked = load("reducedMotion", false);
document.getElementById("reduced-motion").addEventListener("change", event => save("reducedMotion", event.target.checked));

function updateReliableLossControls() {
    const lossEnabled = document.getElementById("reliable-protocol").value === "Go-Back-N ARQ";
    const loss = document.getElementById("reliable-loss");
    const sequence = document.getElementById("reliable-loss-sequence");
    loss.disabled = !lossEnabled;
    if (!lossEnabled) loss.checked = false;
    sequence.disabled = !lossEnabled || !loss.checked;
}

document.getElementById("reliable-protocol").addEventListener("change", updateReliableLossControls);
document.getElementById("reliable-loss").addEventListener("change", updateReliableLossControls);
updateReliableLossControls();

document.getElementById("topology-link").addEventListener("change", renderTopology);
document.getElementById("topology-router").addEventListener("change", renderTopology);
document.getElementById("fail-link").addEventListener("click", async () => {
    const [first, second] = document.getElementById("topology-link").value.split("|");
    if (!state.failedLinks.some(link => linkKey(...link) === linkKey(first, second))) state.failedLinks.push([first, second]);
    save("failedLinks", state.failedLinks);
    addActivity(`Simulated link failure: ${label(first)} ↔ ${label(second)}.`);
    await refreshTopology();
});
document.getElementById("restore-link").addEventListener("click", async () => {
    const selected = document.getElementById("topology-link").value;
    state.failedLinks = state.failedLinks.filter(link => linkKey(...link) !== selected);
    save("failedLinks", state.failedLinks);
    await refreshTopology();
});
document.getElementById("fail-router").addEventListener("click", async () => {
    const router = document.getElementById("topology-router").value;
    if (!state.failedNodes.includes(router)) state.failedNodes.push(router);
    save("failedNodes", state.failedNodes);
    addActivity(`Simulated router failure: ${label(router)}.`);
    await refreshTopology();
});
document.getElementById("restore-router").addEventListener("click", async () => {
    const router = document.getElementById("topology-router").value;
    state.failedNodes = state.failedNodes.filter(node => node !== router);
    save("failedNodes", state.failedNodes);
    await refreshTopology();
});
document.getElementById("restore-all").addEventListener("click", async () => {
    state.failedLinks = [];
    state.failedNodes = [];
    save("failedLinks", []);
    save("failedNodes", []);
    addActivity("Restored all simulated failures.");
    await refreshTopology();
});

document.getElementById("check-path").addEventListener("click", async () => {
    try {
        const data = await api("/api/paths", {
            source: document.getElementById("path-source").value,
            destination: document.getElementById("path-destination").value,
            failedLinks: state.failedLinks,
            failedNodes: state.failedNodes
        });
        showResult("path-result", data.paths?.length
            ? `<strong>${data.paths.length} active path(s)</strong>${data.paths.map((path, index) => `<p>${index + 1}. ${path.map(node => escapeHtml(label(node, true))).join(" → ")}</p>`).join("")}`
            : "<strong>No active path connects these services.</strong>", data.paths?.length ? "success" : "warning");
    } catch (error) { displayError("path-result", error); }
});

document.getElementById("routing-form").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        const data = await api("/api/routing", {
            source: document.getElementById("routing-source").value,
            destination: document.getElementById("routing-destination").value,
            previewFailure: document.getElementById("routing-preview").checked,
            failedLink: document.getElementById("routing-failure-link").value.split("|"),
            failedLinks: state.failedLinks,
            failedNodes: state.failedNodes
        });
        const format = route => route?.length ? route.map(node => escapeHtml(label(node, true))).join(" → ") : "Unavailable";
        showResult("routing-result", `<h2>Route comparison</h2><p><strong>Dijkstra:</strong> ${format(data.dijkstraPath)}${data.dijkstraCost == null ? "" : ` · ${Number(data.dijkstraCost).toFixed(2)} ms`}</p><p><strong>Distance Vector:</strong> ${format(data.distanceVectorPath)}${data.distanceVectorCost == null ? "" : ` · ${Number(data.distanceVectorCost).toFixed(2)} ms`}</p><p>Converged in ${escapeHtml(data.convergenceRound)} rounds.</p>${data.after ? `<hr><h3>After link failure</h3><p><strong>Dijkstra:</strong> ${format(data.after.dijkstraPath)}</p><p><strong>Distance Vector:</strong> ${format(data.after.distanceVectorPath)}</p>` : ""}`, "success");
        if (typeof Plotly !== "undefined" && data.convergenceHistory) Plotly.react("routing-chart", [{ x: data.convergenceHistory.map(row => row.round), y: data.convergenceHistory.map(row => row.cost), type: "scatter", mode: "lines+markers", name: "Advertised route cost", line: { color: "#36c5e8" } }], { height: 300, paper_bgcolor: "#0c1928", plot_bgcolor: "#0c1928", font: { color: "#dce8f1" }, xaxis: { title: "Exchange round" }, yaxis: { title: "Route cost (ms)" } }, { responsive: true, displaylogo: false });
    } catch (error) { displayError("routing-result", error); }
});

document.getElementById("message-form").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        state.messageSequence += 1;
        const data = await api("/api/messages/queue", {
            queue: state.messages,
            sequence: state.messageSequence,
            source: document.getElementById("message-source").value,
            destination: document.getElementById("message-destination").value,
            content: document.getElementById("message-content").value,
            priority: document.getElementById("message-priority").value
        });
        state.messages = data.queue;
        save("messages", state.messages);
        save("messageSequence", state.messageSequence);
        renderQueue();
        addActivity(`Queued ${data.message.messageId} (${data.message.priority}).`);
        showResult("message-result", `<strong>${escapeHtml(data.message.messageId)} added to the priority queue.</strong>`, "success");
    } catch (error) { displayError("message-result", error); }
});
document.getElementById("process-message").addEventListener("click", async () => {
    try {
        const data = await api("/api/messages/process", { queue: state.messages, failedLinks: state.failedLinks, failedNodes: state.failedNodes });
        state.messages = data.queue;
        state.packetEvents.unshift(data.event);
        state.packetEvents = state.packetEvents.slice(0, 500);
        save("messages", state.messages);
        save("packetEvents", state.packetEvents);
        renderQueue();
        renderMonitor();
        await renderAnalytics();
        addActivity(`${data.event.messageId}: ${data.event.status.toLowerCase()}.`);
        showResult("message-result", `<strong>${escapeHtml(data.event.messageId)} · ${escapeHtml(data.event.status)}</strong><p>Route: ${(data.event.route || []).map(node => escapeHtml(label(node, true))).join(" → ") || "Unavailable"}${data.event.transmissionDelayMs == null ? "" : ` · ${Number(data.event.transmissionDelayMs).toFixed(2)} ms`}</p>`, data.event.status === "Delivered" ? "success" : "warning");
    } catch (error) { displayError("message-result", error); }
});

document.getElementById("crc-form").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        const data = await api("/api/crc", {
            dataBits: document.getElementById("crc-data").value,
            generator: document.getElementById("crc-generator").value,
            injectError: document.getElementById("crc-corrupt").checked,
            bitPosition: Number(document.getElementById("crc-position").value)
        });
        const encoding = data.encoding, verification = data.verification;
        const steps = rows => `<table><thead><tr><th>Position</th><th>Window before</th><th>Operation</th><th>Window after</th></tr></thead><tbody>${rows.map(step => `<tr><td>${step.position}</td><td>${escapeHtml(step.before)}</td><td>${escapeHtml(step.operation)}</td><td>${escapeHtml(step.after)}</td></tr>`).join("")}</tbody></table>`;
        showResult("crc-result", `<div class="metric-grid"><div class="metric"><span class="metric-label">Generator degree</span><strong class="metric-value">${encoding.generator.length - 1}</strong></div><div class="metric"><span class="metric-label">CRC remainder</span><strong class="metric-value">${escapeHtml(encoding.remainder)}</strong></div><div class="metric"><span class="metric-label">Transmitted frame</span><strong class="metric-value">${escapeHtml(encoding.transmittedFrame)}</strong></div><div class="metric"><span class="metric-label">Received remainder</span><strong class="metric-value">${escapeHtml(verification.remainder)}</strong></div></div><p><strong>${verification.valid ? "Frame accepted" : "Corruption detected"}</strong> · Received frame: <code>${escapeHtml(verification.receivedFrame)}</code></p><details><summary>Encoding division steps</summary>${steps(encoding.steps)}</details><details><summary>Verification division steps</summary>${steps(verification.steps)}</details>`, verification.valid ? "success" : "warning");
    } catch (error) { displayError("crc-result", error); }
});

document.getElementById("reliable-form").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        const data = await api("/api/reliable", {
            protocol: document.getElementById("reliable-protocol").value,
            packetCount: Number(document.getElementById("reliable-count").value),
            windowSize: Number(document.getElementById("reliable-window").value),
            lostPacket: document.getElementById("reliable-loss").checked ? Number(document.getElementById("reliable-loss-sequence").value) : null,
            source: document.getElementById("reliable-source").value,
            destination: document.getElementById("reliable-destination").value,
            failedLinks: state.failedLinks,
            failedNodes: state.failedNodes
        });
        state.latestReliable = data;
        const result = data.result;
        showResult("reliable-result", `<div class="metric-grid"><div class="metric"><span class="metric-label">Acknowledged</span><strong class="metric-value">${result.totalAcknowledged}/${result.packetCount}</strong></div><div class="metric"><span class="metric-label">Window size</span><strong class="metric-value">${result.windowSize}</strong></div><div class="metric"><span class="metric-label">Rounds</span><strong class="metric-value">${result.rounds?.length ?? result.batches?.length}</strong></div><div class="metric"><span class="metric-label">Retransmissions</span><strong class="metric-value">${result.retransmissionCount ?? 0}</strong></div></div><p>Selected route: ${(data.route || []).map(node => escapeHtml(label(node, true))).join(" → ")}</p>`, "success");
        const rounds = result.rounds || result.batches || [];
        if (typeof Plotly !== "undefined") Plotly.react("reliable-chart", [{ x: rounds.map(round => round.roundNumber), y: rounds.map(round => round.cumulativeAck ?? round.baseAfterAck - 1), type: "scatter", mode: "lines+markers", name: "Cumulative ACK", line: { color: "#55c79a" } }], { height: 350, paper_bgcolor: "#0c1928", plot_bgcolor: "#0c1928", font: { color: "#dce8f1" }, xaxis: { title: "Transmission round", dtick: 1 }, yaxis: { title: "Acknowledged packets" } }, { responsive: true, displaylogo: false });
        addActivity(`${document.getElementById("reliable-protocol").value} simulation acknowledged ${result.totalAcknowledged}/${result.packetCount} packets.`);
    } catch (error) { displayError("reliable-result", error); }
});

document.getElementById("congestion-form").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        const data = await api("/api/congestion", {
            arrivals: document.getElementById("bucket-arrivals").value,
            capacity: Number(document.getElementById("bucket-capacity").value),
            outputRate: Number(document.getElementById("bucket-rate").value)
        });
        const peakTick = data.result.steps.reduce((peak, step) =>
            step.queuedBeforeLeak > data.result.steps[peak - 1].queuedBeforeLeak ? step.tick : peak, 1);
        state.latestBucket = {
            ...data,
            router: document.getElementById("congestion-router").value,
            selectedTick: peakTick
        };
        save("latestBucket", state.latestBucket);
        const result = data.result;
        showResult("congestion-result", `<div class="metric-grid"><div class="metric"><span class="metric-label">Incoming</span><strong class="metric-value">${result.totalArrivals}</strong></div><div class="metric"><span class="metric-label">Admitted</span><strong class="metric-value">${result.totalAdmitted}</strong></div><div class="metric"><span class="metric-label">Transmitted</span><strong class="metric-value">${result.totalTransmitted}</strong></div><div class="metric"><span class="metric-label">Dropped</span><strong class="metric-value">${result.totalDropped}</strong></div><div class="metric"><span class="metric-label">Status</span><strong class="metric-value">${escapeHtml(result.congestionStatus)}</strong></div></div><label>Inspect router queue snapshot <input id="bucket-tick" type="range" min="1" max="${result.steps.length}" value="${peakTick}"></label><strong id="bucket-slot-value"></strong><div id="queue-snapshot"></div><table><thead><tr><th>Slot</th><th>Arrivals</th><th>Queued</th><th>Sent</th><th>Dropped</th><th>Remaining</th></tr></thead><tbody>${result.steps.map(step => `<tr><td>${step.tick}</td><td>${step.arrivals}</td><td>${step.queuedBeforeLeak}</td><td>${step.transmitted}</td><td>${step.dropped}</td><td>${step.queuedAfterLeak}</td></tr>`).join("")}</tbody></table>`, result.totalDropped ? "warning" : "success");
        document.getElementById("bucket-tick").addEventListener("input", renderQueueSnapshot);
        renderQueueSnapshot();
        if (typeof Plotly !== "undefined") Plotly.react("congestion-chart", [
            { x: result.steps.map(step => step.tick), y: result.steps.map(step => step.arrivals), type: "bar", name: "Incoming", marker: { color: "#3984a0" } },
            { x: result.steps.map(step => step.tick), y: result.steps.map(step => step.transmitted), type: "bar", name: "Transmitted", marker: { color: "#41a982" } },
            { x: result.steps.map(step => step.tick), y: result.steps.map(step => step.dropped), type: "bar", name: "Dropped", marker: { color: "#c65b5e" } },
            { x: result.steps.map(step => step.tick), y: result.steps.map(step => step.queuedBeforeLeak), type: "scatter", mode: "lines+markers", name: "Queue before output", line: { color: "#e2a04b" }, yaxis: "y2" }
        ], { barmode: "group", height: 360, paper_bgcolor: "#0c1928", plot_bgcolor: "#0c1928", font: { color: "#dce8f1" }, xaxis: { title: "Time slot", dtick: 1 }, yaxis: { title: "Packets" }, yaxis2: { overlaying: "y", side: "right", title: "Queue" }, legend: { orientation: "h" } }, { responsive: true, displaylogo: false });
        addActivity(`Leaky Bucket: ${result.totalDropped} packet(s) dropped.`);
        renderAnalytics();
    } catch (error) { displayError("congestion-result", error); }
});

document.getElementById("comparison-form").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        const data = await api("/api/congestion/compare", {
            arrivals: document.getElementById("compare-arrivals").value,
            capacity: Number(document.getElementById("compare-capacity").value),
            normalRate: Number(document.getElementById("compare-normal-rate").value),
            stressRate: Number(document.getElementById("compare-stress-rate").value)
        });
        showResult("comparison-result", `<div class="split">${["normal", "stress"].map(key => {
            const result = data[key];
            return `<div><h3>${key === "normal" ? "Normal service" : "Reduced-service stress"}</h3><p>Transmitted: ${result.totalTransmitted} · Dropped: ${result.totalDropped} · Congested slots: ${result.congestedSlots}/${result.steps.length}</p></div>`;
        }).join("")}</div>`, "success");
    } catch (error) { displayError("comparison-result", error); }
});

document.getElementById("monitor-status").addEventListener("change", renderMonitor);
document.getElementById("monitor-priority").addEventListener("change", renderMonitor);
document.getElementById("packet-form").addEventListener("submit", async event => {
    event.preventDefault();
    try {
        state.lastPacketRequest = {
            source: document.getElementById("packet-source").value,
            destination: document.getElementById("packet-destination").value,
            message: document.getElementById("packet-message").value,
            injectPacketLoss: document.getElementById("packet-loss").checked
        };
        const data = await api("/api/packet", {
            ...state.lastPacketRequest,
            failedLinks: state.failedLinks,
            failedNodes: state.failedNodes
        });
        state.lastPacketPlan = data;
        showResult("packet-result", `<h2>Transmission plan</h2><p><strong>Route:</strong> ${data.route.map(node => escapeHtml(label(node, true))).join(" → ")}</p><p>Packet size: ${data.packetSizeBytes} bytes · DATA one-way: ${Number(data.oneWayDelayMs).toFixed(2)} ms · ACK return: ${Number(data.acknowledgementDelayMs).toFixed(2)} ms · Estimated delivery: ${Number(data.estimatedDeliveryDelayMs).toFixed(2)} ms · Retransmissions: ${data.retransmissions}</p>`, "success");
        renderNetworkChart("infrastructure-chart", true);
        addActivity(`Prepared DATA/ACK exchange: ${label(data.source)} → ${label(data.destination)}.`);
    } catch (error) { displayError("packet-result", error); }
});

async function start() {
    document.body.classList.add("loading");
    try {
        await refreshTopology();
        renderMonitor();
        await renderAnalytics();
    } catch (error) {
        showNotice(`Unable to load the simulator: ${error.message}`, true);
    } finally {
        document.body.classList.remove("loading");
    }
}

start();
