from dataclasses import dataclass
import math
from typing import Hashable

import networkx as nx


@dataclass(frozen=True)
class RouteEntry:
    cost: float | None
    next_hop: Hashable | None


@dataclass(frozen=True)
class DistanceVectorSnapshot:
    round_number: int
    tables: dict[Hashable, dict[Hashable, RouteEntry]]


@dataclass(frozen=True)
class DistanceVectorResult:
    tables: dict[Hashable, dict[Hashable, RouteEntry]]
    history: tuple[DistanceVectorSnapshot, ...]
    converged: bool

    @property
    def convergence_round(self) -> int:
        return self.history[-1].round_number


def simulate_distance_vector(
    graph: nx.Graph,
    weight: str = "delay_ms",
) -> DistanceVectorResult:
    if graph.is_directed() or graph.is_multigraph():
        raise ValueError("Distance Vector simulation requires a simple undirected graph.")
    if not isinstance(weight, str) or not weight:
        raise ValueError("A non-empty edge weight attribute is required.")

    routing_graph = nx.Graph()
    routing_graph.add_nodes_from(
        (node, data.copy())
        for node, data in graph.nodes(data=True)
        if data.get("status", "active") == "active"
    )
    for first, second, data in graph.edges(data=True):
        if (
            first not in routing_graph
            or second not in routing_graph
            or data.get("status", "active") != "active"
        ):
            continue
        edge_cost = data.get(weight)
        if (
            not isinstance(edge_cost, (int, float))
            or isinstance(edge_cost, bool)
            or not math.isfinite(edge_cost)
            or edge_cost < 0
        ):
            raise ValueError(
                f"Active link {first!r}–{second!r} needs a finite, non-negative "
                f"{weight!r} cost."
            )
        routing_graph.add_edge(first, second, **{weight: float(edge_cost)})

    nodes = tuple(routing_graph.nodes)
    costs = {
        node: {destination: math.inf for destination in nodes}
        for node in nodes
    }
    next_hops = {
        node: {destination: None for destination in nodes}
        for node in nodes
    }
    for node in nodes:
        costs[node][node] = 0.0
        for neighbor, edge_data in routing_graph[node].items():
            costs[node][neighbor] = edge_data[weight]
            next_hops[node][neighbor] = neighbor

    def make_snapshot(round_number: int) -> DistanceVectorSnapshot:
        tables = {
            node: {
                destination: RouteEntry(
                    cost=cost if math.isfinite(cost) else None,
                    next_hop=next_hops[node][destination],
                )
                for destination, cost in destination_costs.items()
            }
            for node, destination_costs in costs.items()
        }
        return DistanceVectorSnapshot(round_number, tables)

    history = [make_snapshot(0)]
    converged = False
    for round_number in range(1, max(2, len(nodes) + 1)):
        updated_costs = {node: values.copy() for node, values in costs.items()}
        updated_next_hops = {node: values.copy() for node, values in next_hops.items()}
        changed = False

        for node in nodes:
            for destination in nodes:
                for neighbor, edge_data in routing_graph[node].items():
                    neighbor_cost = costs[neighbor][destination]
                    if not math.isfinite(neighbor_cost):
                        continue
                    candidate = edge_data[weight] + neighbor_cost
                    if candidate < updated_costs[node][destination]:
                        updated_costs[node][destination] = candidate
                        updated_next_hops[node][destination] = neighbor
                        changed = True

        costs = updated_costs
        next_hops = updated_next_hops
        history.append(make_snapshot(round_number))
        if not changed:
            converged = True
            break

    return DistanceVectorResult(
        tables=history[-1].tables,
        history=tuple(history),
        converged=converged,
    )


def get_distance_vector_path(
    result: DistanceVectorResult,
    source: Hashable,
    destination: Hashable,
) -> list[Hashable]:
    if source not in result.tables or destination not in result.tables[source]:
        raise ValueError("Source and destination must be active nodes in the routing tables.")
    if result.tables[source][destination].cost is None:
        return []

    path = [source]
    visited = {source}
    current = source
    for _ in range(len(result.tables)):
        if current == destination:
            return path
        next_hop = result.tables[current][destination].next_hop
        if next_hop is None or next_hop in visited:
            raise RuntimeError("Converged routing tables contain an invalid next-hop chain.")
        path.append(next_hop)
        visited.add(next_hop)
        current = next_hop

    raise RuntimeError("Distance Vector path exceeded the number of active network nodes.")
