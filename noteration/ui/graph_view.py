"""
noteration/ui/graph_view.py

Graph visualization widget menggunakan QGraphicsView.
Mirip local graph di Obsidian - interaktif dengan zoom, pan, drag node.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView,
    QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsTextItem, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QFont, QColor, QPen, QBrush, QPainter, QWheelEvent, QPalette,
)

from noteration.db.link_graph import LinkGraph
from noteration.db.layout_engine import LayoutEngine


class GraphNodeItem(QGraphicsEllipseItem):
    def __init__(self, node_name: str, radius: float = 12.0, palette: QPalette | None = None) -> None:
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.node_name = node_name
        self._palette = palette

        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        self._update_colors()
        self.setPen(QPen(Qt.PenStyle.NoPen))

    def _update_colors(self) -> None:
        is_dark = self._palette.color(QPalette.ColorRole.Window).lightness() < 128 if self._palette else False
        
        if is_dark:
            self._default_brush = QBrush(QColor("#64B5F6"))
            self._hover_brush = QBrush(QColor("#90CAF9"))
            self._current_brush = QBrush(QColor("#FF7043"))
            self._orphan_brush = QBrush(QColor("#757575"))
        else:
            self._default_brush = QBrush(QColor("#42A5F5"))
            self._hover_brush = QBrush(QColor("#1E88E5"))
            self._current_brush = QBrush(QColor("#FF5722"))
            self._orphan_brush = QBrush(QColor("#BDBDBD"))
        
        self.setBrush(self._default_brush)

    def set_highlight(self, is_current: bool = False, is_orphan: bool = False) -> None:
        if is_current:
            self.setBrush(self._current_brush)
        elif is_orphan:
            self.setBrush(self._orphan_brush)
        else:
            self.setBrush(self._default_brush)

    def hoverEnterEvent(self, event) -> None:
        self.setBrush(self._hover_brush)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        super().hoverLeaveEvent(event)


class GraphEdgeItem(QGraphicsLineItem):
    def __init__(self, x1: float, y1: float, x2: float, y2: float, color: QColor) -> None:
        super().__init__(x1, y1, x2, y2)
        pen = QPen(color)
        pen.setWidth(2)
        self.setPen(pen)


class GraphLabelItem(QGraphicsTextItem):
    def __init__(self, text: str, x: float, y: float, color: QColor) -> None:
        super().__init__(text)
        self.setPos(x, y)
        self.setDefaultTextColor(color)
        font = QFont("SansSerif", 10, QFont.Weight.Bold)
        self.setFont(font)


class GraphView(QWidget):
    """Graph visualization widget."""

    node_clicked = Signal(str)
    node_double_clicked = Signal(str)

    def __init__(
        self,
        graph: LinkGraph,
        vault_path: Path,
        current_note: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._graph = graph
        self._vault_path = vault_path
        self._current_note = current_note

        self._node_items: dict[str, GraphNodeItem] = {}
        self._edge_items: list[QGraphicsLineItem] = []
        self._label_items: dict[str, GraphLabelItem] = {}
        self._adj: dict[str, set[str]] = {}

        self._engine: LayoutEngine | None = None
        self._running = False
        self._show_labels = True
        self._show_orphans = True
        self._animation = True
        self._iterations_per_frame = 3
        self._max_frames = 150  # Limit total animation time
        self._frame_count = 0

        self._scene_width = 600.0
        self._scene_height = 400.0

        self._setup_ui()
        self._build_scene()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background:palette(window);")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Graph")
        title.setStyleSheet("font-weight:600;font-size:12px;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self._btn_fit = QPushButton("⊡ Fit")
        self._btn_fit.setFixedSize(40, 24)
        self._btn_fit.setStyleSheet("font-size:10px;")
        self._btn_fit.clicked.connect(self._fit_to_view)
        h_layout.addWidget(self._btn_fit)

        self._btn_orphans = QPushButton("◎")
        self._btn_orphans.setFixedSize(24, 24)
        self._btn_orphans.setCheckable(True)
        self._btn_orphans.setChecked(self._show_orphans)
        self._btn_orphans.setStyleSheet("font-size:11px;")
        self._btn_orphans.toggled.connect(self._toggle_orphans)
        h_layout.addWidget(self._btn_orphans)

        layout.addWidget(header)

        self._scene = QGraphicsScene(self)
        self._update_scene_background()
        self._scene.setSceneRect(0, 0, self._scene_width, self._scene_height)

        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._view.wheelEvent = self._on_wheel  # type: ignore[method-assign]

        # Install mouse press handler for node clicks
        self._view.mousePressEvent = self._on_mouse_press  # type: ignore[method-assign]

        layout.addWidget(self._view)

    def _update_scene_background(self) -> None:
        bg = self.palette().color(QPalette.ColorRole.Base)
        self._scene.setBackgroundBrush(bg)

    def changeEvent(self, event) -> None:
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.PaletteChange:
            self._update_scene_background()
            self.refresh()
        super().changeEvent(event)

    def _build_scene(self) -> None:
        nodes = self._graph.all_nodes()
        if not nodes:
            return

        self._adj = {}
        for node in nodes:
            self._adj[node] = set(self._graph.forward_links(node))

        orphans = set(self._graph.orphans())

        self._engine = LayoutEngine(self._adj, self._scene_width, self._scene_height)
        self._engine.initialize_from_adj(self._adj)

        self._render_graph(orphans)

        if self._animation:
            self._start_animation()

    def _render_graph(self, orphans: set[str]) -> None:
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()
        self._label_items.clear()

        pal = self.palette()
        edge_color = pal.color(QPalette.ColorRole.Mid)
        label_color = pal.color(QPalette.ColorRole.Text)

        if self._engine:
            positions = self._engine.get_positions()
        else:
            positions = None
        if not positions:
            return

        for src, dsts in self._adj.items():
            if src not in positions:
                continue
            sx, sy = positions[src]
            for dst in dsts:
                if dst not in positions:
                    continue
                dx, dy = positions[dst]
                edge = GraphEdgeItem(sx, sy, dx, dy, edge_color)
                edge.setZValue(-1)
                self._scene.addItem(edge)
                self._edge_items.append(edge)

        for node, (x, y) in positions.items():
            node_item = GraphNodeItem(node, palette=pal)
            node_item.setPos(x, y)

            is_orphan = node in orphans
            if node == self._current_note:
                node_item.set_highlight(is_current=True)
            elif is_orphan and not self._show_orphans:
                node_item.setVisible(False)

            self._scene.addItem(node_item)
            self._node_items[node] = node_item

            if self._show_labels:
                label = GraphLabelItem(node, x + 14, y - 6, label_color)
                if is_orphan and not self._show_orphans:
                    label.setVisible(False)
                self._scene.addItem(label)
                self._label_items[node] = label

    def _start_animation(self) -> None:
        self._running = True
        self._frame_count = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate_step)
        self._anim_timer.start(30)

    def _animate_step(self) -> None:
        if not self._engine or not self._running:
            return

        self._frame_count += 1
        positions_before = self._engine.get_positions()

        for _ in range(self._iterations_per_frame):
            next(self._engine.iterate(1))

        positions_after = self._engine.get_positions()

        max_delta = 0.0
        for node in positions_before:
            if node not in positions_after:
                continue
            x1, y1 = positions_before[node]
            x2, y2 = positions_after[node]
            delta = abs(x2 - x1) + abs(y2 - y1)
            max_delta = max(max_delta, delta)

        for node, item in self._node_items.items():
            if node in positions_after:
                x, y = positions_after[node]
                item.setPos(x, y)

        for node, label in self._label_items.items():
            if node in positions_after:
                x, y = positions_after[node]
                label.setPos(x + 14, y - 6)

        # Update edge positions
        idx = 0
        for src, dsts in self._adj.items():
            if src not in positions_after:
                continue
            sx, sy = positions_after[src]
            for dst in dsts:
                if dst not in positions_after:
                    continue
                dx, dy = positions_after[dst]
                if idx < len(self._edge_items):
                    self._edge_items[idx].setLine(sx, sy, dx, dy)
                    idx += 1

        # Stop if converged or limit reached
        if max_delta < 0.1 or self._frame_count >= self._max_frames:
            self._running = False
            self._anim_timer.stop()
            self._finalize_layout()

    def _finalize_layout(self) -> None:
        if self._engine:
            self._engine.center_graph()
            positions = self._engine.get_positions()
            for node, item in self._node_items.items():
                if node in positions:
                    x, y = positions[node]
                    item.setPos(x, y)
            for node, label in self._label_items.items():
                if node in positions:
                    x, y = positions[node]
                    label.setPos(x + 14, y - 6)

    def _fit_to_view(self) -> None:
        self._view.resetTransform()
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _toggle_orphans(self, checked: bool) -> None:
        self._show_orphans = checked
        orphans = set(self._graph.orphans())
        for node, item in self._node_items.items():
            is_orphan = node in orphans
            item.setVisible(not is_orphan or checked)
            if node in self._label_items:
                self._label_items[node].setVisible(not is_orphan or checked)

    def _on_mouse_press(self, event) -> None:
        # Check if a node was clicked
        item = self._view.itemAt(event.pos())
        if isinstance(item, GraphNodeItem):
            self.node_clicked.emit(item.node_name)
        # Pass to default handler
        from PySide6.QtWidgets import QGraphicsView
        QGraphicsView.mousePressEvent(self._view, event)

    def _on_wheel(self, event: QWheelEvent) -> None:
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self._view.scale(zoom_factor, zoom_factor)
        else:
            self._view.scale(1 / zoom_factor, 1 / zoom_factor)
        event.accept()

    def set_current_note(self, note_stem: str) -> None:
        self._current_note = note_stem
        orphans = set(self._graph.orphans())
        for node, item in self._node_items.items():
            is_orphan = node in orphans
            if node == note_stem:
                item.set_highlight(is_current=True)
            elif is_orphan:
                item.set_highlight(is_orphan=True)

    def refresh(self) -> None:
        self._build_scene()
        # Apply current orphan toggle state
        self._toggle_orphans(self._show_orphans)

    def set_viewport_size(self, width: float, height: float) -> None:
        self._scene_width = width
        self._scene_height = height
        self._scene.setSceneRect(0, 0, width, height)
        if self._engine:
            self._engine.set_viewport(width, height)