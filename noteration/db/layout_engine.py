"""
noteration/db/layout_engine.py

Force-directed graph layout algorithm (spring-embedder).
Computed on CPU - tidak perlu external libraries.

Algorithm:
  - Repulsion: nodes saling tolak (Coulomb inverse-square)
  - Attraction: connected nodes menarik (Hooke's spring)
  - Centering: pull ke tengah viewport
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Iterator

Point = tuple[float, float]


class LayoutEngine:
    """
    Force-directed layout calculator.

    Usage:
        engine = LayoutEngine(graph)  # graph: dict{node: [neighbors]}
        for positions in engine.iterate(max_iter=100):
            print(positions)  # dict{node: (x, y)}
    """

    def __init__(
        self,
        adj: dict[str, set[str]] | None = None,
        width: float = 800.0,
        height: float = 600.0,
    ) -> None:
        self._adj = adj or {}
        self._width = width
        self._height = height

        self._positions: dict[str, Point] = {}
        self._velocities: dict[str, Point] = {}

        self.repulsion: float = 6000.0
        self.attraction: float = 0.015
        self.damping: float = 0.8
        self.center_pull: float = 0.05
        self.min_distance: float = 40.0
        self.max_velocity: float = 15.0

        # Cooling factor to ensure convergence
        self.temperature: float = 1.0
        self.cooling_rate: float = 0.98
        self.repulsion_cutoff: float = 250.0  # Cutoff distance for O(N^2) repulsion

    def set_graph(self, adj: dict[str, set[str]]) -> None:
        """Update graph structure."""
        self._adj = adj
        missing = set(adj.keys()) - set(self._positions.keys())
        for node in missing:
            self._initialize_node(node)
        self.temperature = 1.0

    def _initialize_node(self, node: str) -> None:
        """Random position within viewport."""
        x = random.uniform(self._width * 0.2, self._width * 0.8)
        y = random.uniform(self._height * 0.2, self._height * 0.8)
        self._positions[node] = (x, y)
        self._velocities[node] = (0.0, 0.0)

    def _reset_velocities(self) -> None:
        """Reset velocities to zero."""
        for node in self._velocities:
            self._velocities[node] = (0.0, 0.0)

    def iterate(self, iterations: int = 1) -> Iterator[dict[str, Point]]:
        """Run one or more iterations, yield positions each step."""
        nodes = list(self._positions.keys())
        if not nodes:
            return

        for _ in range(iterations):
            forces: dict[str, tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))

            center_x = self._width / 2
            center_y = self._height / 2

            for i, node_a in enumerate(nodes):
                xa, ya = self._positions[node_a]
                fx, fy = forces[node_a]

                # Center pull
                fx += (center_x - xa) * self.center_pull
                fy += (center_y - ya) * self.center_pull

                # Optimized repulsion with cutoff
                for j, node_b in enumerate(nodes):
                    if i == j:
                        continue
                    xb, yb = self._positions[node_b]

                    dx = xa - xb
                    dy = ya - yb
                    
                    # Manhattan distance for quick cutoff check
                    if abs(dx) > self.repulsion_cutoff or abs(dy) > self.repulsion_cutoff:
                        continue
                        
                    dist_sq = dx * dx + dy * dy
                    if dist_sq < 1:
                        dist_sq = 1
                    
                    dist = math.sqrt(dist_sq)
                    if dist > self.repulsion_cutoff:
                        continue

                    repulsion_force = self.repulsion / dist_sq
                    fx += (dx / dist) * repulsion_force
                    fy += (dy / dist) * repulsion_force

                # Attraction (Hooke's law)
                for node_b in self._adj.get(node_a, []):
                    if node_b not in self._positions:
                        continue
                    xb, yb = self._positions[node_b]

                    dx = xb - xa
                    dy = yb - ya
                    dist = math.hypot(dx, dy)
                    if dist < 1:
                        dist = 1

                    if dist < self.min_distance:
                        continue

                    attraction_force = self.attraction * (dist - self.min_distance)
                    fx += (dx / dist) * attraction_force
                    fy += (dy / dist) * attraction_force

                forces[node_a] = (fx, fy)

            # Update positions and apply cooling
            for node in nodes:
                fx, fy = forces[node]
                vx, vy = self._velocities[node]

                # Apply temperature to forces
                vx = (vx + fx * self.temperature) * self.damping
                vy = (vy + fy * self.temperature) * self.damping

                speed = math.hypot(vx, vy)
                max_v = self.max_velocity * self.temperature
                if speed > max_v:
                    scale = max_v / speed
                    vx *= scale
                    vy *= scale

                self._velocities[node] = (vx, vy)

                px, py = self._positions[node]
                px += vx
                py += vy

                # Viewport bounds
                margin = 30
                px = max(margin, min(self._width - margin, px))
                py = max(margin, min(self._height - margin, py))

                self._positions[node] = (px, py)
            
            # Cool down
            self.temperature *= self.cooling_rate
            if self.temperature < 0.005:
                self.temperature = 0.0

            yield dict(self._positions)

    def get_positions(self) -> dict[str, Point]:
        """Get current positions."""
        return dict(self._positions)

    def set_viewport(self, width: float, height: float) -> None:
        """Update viewport size."""
        self._width = width
        self._height = height

    def center_graph(self) -> None:
        """Center all nodes in viewport."""
        if not self._positions:
            return

        xs = [p[0] for p in self._positions.values()]
        ys = [p[1] for p in self._positions.values()]

        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)

        offset_x = self._width / 2 - center_x
        offset_y = self._height / 2 - center_y

        for node in self._positions:
            x, y = self._positions[node]
            self._positions[node] = (
                x + offset_x,
                y + offset_y,
            )

    def initialize_from_adj(self, adj: dict[str, set[str]]) -> None:
        """Initialize positions from adjacency dict."""
        self._adj = adj
        self._positions.clear()
        self._velocities.clear()

        for node in adj:
            self._initialize_node(node)

        center_x = self._width / 2
        center_y = self._height / 2
        nodes = list(adj.keys())
        n = len(nodes)
        if n == 0:
            return

        radius = min(self._width, self._height) * 0.3 / 2
        for i, node in enumerate(nodes):
            angle = 2 * math.pi * i / n
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            self._positions[node] = (x, y)
            self._velocities[node] = (0.0, 0.0)