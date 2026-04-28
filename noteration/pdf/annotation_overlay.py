"""
noteration/pdf/annotation_overlay.py

QWidget transparan yang ditaruh di atas halaman PDF untuk menampilkan:
  - Highlight (rect berwarna semi-transparan)
  - Komentar (ikon sticky note)
  - Bookmark (ikon bookmark)

Interaksi:
  - Klik kanan pada overlay → context menu (hapus, edit, jump to note)
  - Drag untuk membuat highlight baru (saat mode highlight aktif)
  - Klik untuk menambah komentar (saat mode comment aktif)
"""

from __future__ import annotations


from PySide6.QtWidgets import QWidget, QMenu, QDialog, QVBoxLayout, QPlainTextEdit, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QMouseEvent, QPaintEvent,
    QFont, QPainterPath, QPolygonF,
)
import fitz

from noteration.pdf.annotations import Annotation, AnnotationStore


class AnnotationOverlay(QWidget):
    """
    Widget transparan yang di-overlay di atas halaman PDF.
    Koordinat internal dalam PDF points; perlu scale ke pixel saat paint.
    """

    annotation_created = Signal(object)   # Annotation baru
    annotation_deleted = Signal(str)      # ann_id
    annotation_edited = Signal(object)    # Annotation yang diupdate
    jump_to_note_requested = Signal(str)  # path note

    def __init__(
        self,
        papis_key: str,
        page_idx: int,
        store: AnnotationStore,
        page_width_pts: float,
        page_height_pts: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.papis_key = papis_key
        self.page_idx = page_idx
        self._store = store
        self._page_w = page_width_pts
        self._page_h = page_height_pts
        self._fitz_page = None  # PyMuPDF page
        self._page_words: list = []
        self._mode: str = "view"    # "view" | "highlight" | "comment" | "image"

        # State drag
        self._drag_start_pos: QPointF | None = None
        self._drag_end_pos: QPointF | None = None
        self._drag_start_idx: int = -1
        self._drag_end_idx: int = -1
        self._dragging = False

        # Tampilan
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

    def set_fitz_page(self, page) -> None:
        self._fitz_page = page
        if page:
            # words: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
            self._page_words = page.get_text("words")
        else:
            self._page_words = []

    def _extract_text_from_rect(self, rect_pts: list[float]) -> str:
        if self._fitz_page is None:
            return ""
        try:
            x0, y0, x1, y1 = rect_pts
            r = fitz.Rect(x0, y0, x1, y1)
            text = self._fitz_page.get_text("text", clip=r)
            return text.strip() if text else ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """mode: 'view' | 'highlight' | 'comment' | 'image'"""
        self._mode = mode
        if mode in ("highlight", "image"):
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif mode == "comment":
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def refresh(self) -> None:
        self.update()

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _scale(self) -> float:
        """Scale factor: pixel / PDF point."""
        if self._page_w <= 0 or self.width() <= 0:
            return 1.0
        return self.width() / self._page_w

    def _pts_to_px(self, bbox: list[float]) -> QRectF:
        s = self._scale()
        x0, y0, x1, y1 = bbox
        return QRectF(x0 * s, y0 * s, (x1 - x0) * s, (y1 - y0) * s)

    def _px_to_pts(self, px_rect: QRectF) -> list[float]:
        s = self._scale()
        if s <= 0:
            s = 1.0
        return [
            px_rect.x() / s,
            px_rect.y() / s,
            px_rect.right() / s,
            px_rect.bottom() / s,
        ]

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def _find_word_at_pos(self, pos_pts: QPointF) -> int:
        """Cari index kata terdekat dengan posisi (dalam PDF points)."""
        if not self._page_words:
            return -1
        
        px, py = pos_pts.x(), pos_pts.y()
        best_idx = -1
        min_dist = 1e9
        
        # 1. Prioritas: Apakah titik berada di dalam kotak kata?
        for i, w in enumerate(self._page_words):
            # w: (x0, y0, x1, y1, ...)
            if w[0] <= px <= w[2] and w[1] <= py <= w[3]:
                return i
            
        # 2. Sekunder: Cari kata terdekat secara horizontal dengan sedikit toleransi vertikal
        # Ini membantu saat menyorot di antara baris atau di pinggir kata.
        for i, w in enumerate(self._page_words):
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            # Berikan penalti besar pada jarak vertikal (dy) agar tidak mudah lompat baris
            dx = abs(px - cx)
            dy = abs(py - cy)
            
            dist = dx + dy * 4.0
            if dist < min_dist:
                min_dist = dist
                best_idx = i
        
        # Toleransi ditingkatkan ke 150 points (~2 inci) untuk memastikan "snap" bekerja
        return best_idx if min_dist < 150 else -1

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            doc = self._store.load(self.papis_key)
            for ann in doc.for_page(self.page_idx):
                self._paint_annotation(painter, ann)

            # Seleksi preview
            if self._dragging and self._drag_start_pos and self._drag_end_pos:
                if self._mode == "highlight":
                    if self._drag_start_idx != -1 and self._drag_end_idx != -1:
                        self._paint_selection_preview(painter)
                    else:
                        # Fallback preview kotak
                        drag_rect = QRectF(self._drag_start_pos, self._drag_end_pos).normalized()
                        painter.setBrush(QBrush(QColor(255, 235, 59, 80)))
                        painter.setPen(QPen(QColor(255, 193, 7), 1))
                        painter.drawRect(drag_rect)
                elif self._mode == "image":
                    drag_rect = QRectF(self._drag_start_pos, self._drag_end_pos).normalized()
                    painter.setBrush(QBrush(QColor(255, 235, 59, 80)))
                    painter.setPen(QPen(QColor(255, 193, 7), 1))
                    painter.drawRect(drag_rect)
        finally:
            painter.end()

    def _paint_selection_preview(self, painter: QPainter) -> None:
        """Gambar preview seleksi teks yang mengikuti baris secara presisi."""
        start = min(self._drag_start_idx, self._drag_end_idx)
        end = max(self._drag_start_idx, self._drag_end_idx)
        
        s = self._scale()
        color = QColor(255, 235, 59, 130)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Kelompokkan kata terpilih ke dalam baris untuk rendering rapi
        lines: dict[int, list[tuple]] = {}
        for i in range(start, end + 1):
            w_data = self._page_words[i]
            l_key = w_data[6] # line_no
            if l_key not in lines:
                lines[l_key] = []
            lines[l_key].append(w_data)
            
        for l_no in sorted(lines.keys()):
            l_words = lines[l_no]
            lx0 = min(item[0] for item in l_words)
            ly0 = min(item[1] for item in l_words)
            lx1 = max(item[2] for item in l_words)
            ly1 = max(item[3] for item in l_words)
            painter.drawRect(QRectF(lx0*s, ly0*s, (lx1-lx0)*s, (ly1-ly0)*s))

    def _paint_annotation(self, painter: QPainter, ann: Annotation) -> None:
        if ann.type in ("highlight", "image"):
            color = QColor(ann.color)
            color.setAlpha(90)
            painter.setBrush(QBrush(color))
            border_color = QColor(ann.color).darker(140)
            border_color.setAlpha(160)
            painter.setPen(QPen(border_color, 0.5))

            # Prioritaskan quads untuk highlight (teks)
            if ann.type == "highlight" and ann.quads:
                s = self._scale()
                path = QPainterPath()
                for q in ann.quads:
                    # q: [p0.x, p0.y, p1.x, p1.y, p2.x, p2.y, p3.x, p3.y]
                    # Urutan p0(TL), p1(TR), p2(BL), p3(BR)
                    # Poligon harus: TL -> TR -> BR -> BL
                    poly = QPolygonF([
                        QPointF(q[0] * s, q[1] * s), # p0
                        QPointF(q[2] * s, q[3] * s), # p1
                        QPointF(q[6] * s, q[7] * s), # p3
                        QPointF(q[4] * s, q[5] * s)  # p2
                    ])
                    path.addPolygon(poly)
                painter.drawPath(path)
            # Fallback ke rect untuk image atau jika quads highlight tidak ada
            elif ann.rect:
                rect = self._pts_to_px(ann.rect)
                painter.drawRect(rect)

            # Tag label kecil jika ada note
            if ann.note and ann.rect:
                rect = self._pts_to_px(ann.rect)
                painter.setFont(QFont("Arial", 8))
                painter.setPen(QPen(QColor("#555"), 1))
                painter.drawText(
                    int(rect.x()), int(rect.y() - 2),
                    ann.note[:30]
                )

        elif ann.type == "comment" and ann.position:
            s = self._scale()
            cx = ann.position[0] * s
            cy = ann.position[1] * s
            # Sticky note ikon (18×18)
            icon_rect = QRectF(cx - 9, cy - 9, 18, 18)
            painter.setBrush(QBrush(QColor("#FFF9C4")))
            painter.setPen(QPen(QColor("#F9A825"), 1.5))
            painter.drawRoundedRect(icon_rect, 2, 2)
            painter.setFont(QFont("Arial", 7))
            painter.setPen(QPen(QColor("#555")))
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "✏")

        elif ann.type == "bookmark":
            if ann.position:
                s = self._scale()
                cx = ann.position[0] * s
                cy = 0
                painter.setBrush(QBrush(QColor("#EF9F27")))
                painter.setPen(Qt.PenStyle.NoPen)
                # Segitiga bookmark
                triangle = QPolygonF([
                    QPointF(cx - 6, cy),
                    QPointF(cx + 6, cy),
                    QPointF(cx, cy + 12),
                ])
                painter.drawPolygon(triangle)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        s = self._scale()
        pos_pts = QPointF(pos.x() / s, pos.y() / s)

        if event.button() == Qt.MouseButton.LeftButton:
            if self._mode in ("highlight", "image"):
                self._drag_start_pos = pos
                self._drag_end_pos = pos
                self._dragging = True
                
                if self._mode == "highlight":
                    self._drag_start_idx = self._find_word_at_pos(pos_pts)
                    self._drag_end_idx = self._drag_start_idx

            elif self._mode == "comment":
                self._add_comment(pos_pts.x(), pos_pts.y())

            elif self._mode == "view":
                # Cek klik pada anotasi yang ada
                ann = self._hit_test(pos)
                if ann:
                    self._show_annotation_detail(ann)

        elif event.button() == Qt.MouseButton.RightButton:
            ann = self._hit_test(pos)
            self._show_context_menu(event.globalPosition().toPoint(), ann)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._drag_end_pos = event.position()
            
            if self._mode == "highlight":
                s = self._scale()
                pos_pts = QPointF(event.position().x() / s, event.position().y() / s)
                self._drag_end_idx = self._find_word_at_pos(pos_pts)
                
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._dragging = False
            
            if self._mode == "highlight":
                if self._drag_start_idx != -1 and self._drag_end_idx != -1:
                    self._finalize_text_selection()
                elif self._drag_start_pos and self._drag_end_pos:
                    # FALLBACK: Jika tidak ada kata yang terdeteksi, gunakan box selection lama
                    drag_rect = QRectF(self._drag_start_pos, self._drag_end_pos).normalized()
                    if drag_rect.width() > 5 and drag_rect.height() > 5:
                        pts = self._px_to_pts(drag_rect)
                        self._add_highlight(pts)
            elif self._mode == "image":
                if self._drag_start_pos and self._drag_end_pos:
                    drag_rect = QRectF(self._drag_start_pos, self._drag_end_pos).normalized()
                    if drag_rect.width() > 5 and drag_rect.height() > 5:
                        pts = self._px_to_pts(drag_rect)
                        self._add_image_highlight(pts)
            
            self._drag_start_pos = None
            self._drag_end_pos = None
            self._drag_start_idx = -1
            self._drag_end_idx = -1
            self.update()

    def _finalize_text_selection(self) -> None:
        """Kumpulkan quads dan teks dari kata terpilih dan simpan."""
        start = min(self._drag_start_idx, self._drag_end_idx)
        end = max(self._drag_start_idx, self._drag_end_idx)
        
        words = self._page_words[start : end + 1]
        if not words:
            return

        quads = []
        text_parts = []
        lines: dict[int, list[tuple]] = {}
        
        # Bounding box global untuk rect
        all_x0, all_y0 = 1e9, 1e9
        all_x1, all_y1 = -1e9, -1e9

        for w in words:
            # (x0, y0, x1, y1, text, b_no, l_no, w_no)
            all_x0 = min(all_x0, w[0])
            all_y0 = min(all_y0, w[1])
            all_x1 = max(all_x1, w[2])
            all_y1 = max(all_y1, w[3])
            
            l_key = w[6]
            if l_key not in lines:
                lines[l_key] = []
            lines[l_key].append(w)
            text_parts.append(w[4])
            
        for l_no in sorted(lines.keys()):
            l_words = lines[l_no]
            lx0 = min(w[0] for w in l_words)
            ly0 = min(w[1] for w in l_words)
            lx1 = max(w[2] for w in l_words)
            ly1 = max(w[3] for w in l_words)
            # p0, p1, p2, p3 (TL, TR, BL, BR)
            quads.append([lx0, ly0, lx1, ly0, lx0, ly1, lx1, ly1])

        text = " ".join(text_parts)
        rect_pts = [all_x0, all_y0, all_x1, all_y1]
        
        ann = self._store.new_highlight(
            papis_key=self.papis_key,
            page=self.page_idx,
            rect=rect_pts,
            quads=quads,
            text_content=text,
        )
        self.annotation_created.emit(ann)

    # ------------------------------------------------------------------
    # Annotation creation
    # ------------------------------------------------------------------

    def _add_highlight(self, rect_pts: list[float]) -> None:
        try:
            x0, y0, x1, y1 = rect_pts
            fitz_rect = fitz.Rect(x0, y0, x1, y1)
            
            quads: list[list[float]] = []
            text_parts: list[str] = []
            
            if self._fitz_page:
                # Ambil semua kata yang ada di dalam area rect
                # words: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
                words = self._fitz_page.get_text("words", clip=fitz_rect)
                
                # Kelompokkan berdasarkan line_no agar kita bisa buat quad per baris
                lines = {}
                for w in words:
                    l_no = w[6]
                    if l_no not in lines:
                        lines[l_no] = []
                    lines[l_no].append(w)
                    text_parts.append(w[4])
                
                for l_no in sorted(lines.keys()):
                    line_words = lines[l_no]
                    # Gabungkan kata-kata dalam satu baris menjadi satu bounding box baris
                    lx0 = min(w[0] for w in line_words)
                    ly0 = min(w[1] for w in line_words)
                    lx1 = max(w[2] for w in line_words)
                    ly1 = max(w[3] for w in line_words)
                    
                    # Simpan sebagai p0, p1, p2, p3
                    quads.append([lx0, ly0, lx1, ly0, lx0, ly1, lx1, ly1])

            text = " ".join(text_parts)

            ann = self._store.new_highlight(
                papis_key=self.papis_key,
                page=self.page_idx,
                rect=rect_pts,
                quads=quads if quads else None,
                text_content=text or "",
            )
            self.update()
            self.annotation_created.emit(ann)
        except Exception:
            pass

    def _add_image_highlight(self, rect_pts: list[float]) -> None:
        if self._fitz_page is None:
            return

        try:
            x0, y0, x1, y1 = rect_pts

            mat = fitz.Matrix(2.0, 2.0)
            pix = self._fitz_page.get_pixmap(matrix=mat, alpha=False, clip=fitz.Rect(x0, y0, x1, y1))

            image_bytes = pix.tobytes("png")

            ann = self._store.new_highlight(
                papis_key=self.papis_key,
                page=self.page_idx,
                rect=rect_pts,
                text_content="",
                type_="image",
            )
            img_path = self._store.save_image(self.papis_key, ann.id, image_bytes)

            doc = self._store.load(self.papis_key)
            doc.update(ann.id, image_path=img_path)
            self._store.save(self.papis_key)
            self.update()
            self.annotation_created.emit(ann)
        except Exception:
            pass

    def _add_comment(self, x_pts: float, y_pts: float) -> None:
        dlg = CommentDialog(self)
        if dlg.exec():
            note = dlg.get_note()
            ann = self._store.new_comment(
                papis_key=self.papis_key,
                page=self.page_idx,
                position=[x_pts, y_pts],
                note=note,
            )
            self.update()
            self.annotation_created.emit(ann)

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _hit_test(self, pos: QPointF) -> Annotation | None:
        doc = self._store.load(self.papis_key)
        for ann in reversed(doc.for_page(self.page_idx)):
            if ann.type in ("highlight", "image") and ann.rect:
                rect = self._pts_to_px(ann.rect)
                if rect.contains(pos):
                    return ann
            elif ann.type == "comment" and ann.position:
                s = self._scale()
                cx = ann.position[0] * s
                cy = ann.position[1] * s
                if abs(pos.x() - cx) < 12 and abs(pos.y() - cy) < 12:
                    return ann
        return None

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, global_pos, ann: Annotation | None) -> None:
        menu = QMenu(self)

        if ann:
            edit_act = menu.addAction("Edit Catatan…")
            delete_act = menu.addAction("Hapus Anotasi")
            menu.addSeparator()
            if ann.linked_notes:
                jump_act = menu.addAction("Lompat ke Catatan Tertaut")
            else:
                jump_act = None
        else:
            edit_act = None
            delete_act = None
            jump_act = None

        chosen = menu.exec(global_pos)

        if not chosen:
            return
        if ann and chosen == delete_act:
            self._store.load(self.papis_key).remove(ann.id)
            self._store.save(self.papis_key)
            self.update()
            self.annotation_deleted.emit(ann.id)
        elif ann and chosen == edit_act:
            dlg = CommentDialog(self, initial_text=ann.note)
            if dlg.exec():
                self._store.load(self.papis_key).update(ann.id, note=dlg.get_note())
                self._store.save(self.papis_key)
                self.update()
                self.annotation_edited.emit(ann)
        elif ann and jump_act and chosen == jump_act:
            if ann.linked_notes:
                self.jump_to_note_requested.emit(ann.linked_notes[0])

    # ------------------------------------------------------------------
    # Detail popup
    # ------------------------------------------------------------------

    def _show_annotation_detail(self, ann: Annotation) -> None:
        dlg = CommentDialog(self, initial_text=ann.note, read_only=False)
        if dlg.exec():
            new_note = dlg.get_note()
            if new_note != ann.note:
                self._store.load(self.papis_key).update(ann.id, note=new_note)
                self._store.save(self.papis_key)
                self.update()
                self.annotation_edited.emit(ann)


class CommentDialog(QDialog):
    """Dialog sederhana untuk input / edit teks catatan pada anotasi."""

    def __init__(self, parent=None, initial_text: str = "", read_only: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Catatan Anotasi")
        self.resize(360, 180)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Catatan:"))

        self._text = QPlainTextEdit()
        self._text.setPlainText(initial_text)
        self._text.setReadOnly(read_only)
        layout.addWidget(self._text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Simpan")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Batal")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def get_note(self) -> str:
        return self._text.toPlainText().strip()
