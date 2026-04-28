"""
noteration/editor/syntax_highlighter.py

QSyntaxHighlighter untuk Markdown — mencakup semua fitur Basic Syntax
sesuai spec markdownguide.org/basic-syntax.

Fitur yang ditambahkan vs versi sebelumnya:
  - Heading alternatif (=== dan --- setelah teks)
  - Bold+Italic kombinasi ***text*** dan ___text___
  - Nested blockquote >>
  - Unordered list dengan +
  - Indented code block (4 spasi / 1 tab)
  - Horizontal rule *** dan ___ (sebelumnya hanya ---)
  - Image ![alt](url)
  - Autolink <url> dan <email>
  - Reference-style link [text][label] dan definisi [label]: url
  - Escape character \\*  \\_ dll
  - HTML inline tags <em>, <strong>, <br>, <a ...>, dst
  - Line break trailing (2+ spasi di akhir baris — ditandai secara visual)
"""

from __future__ import annotations

import re
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextDocument,
)


class MarkdownHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter Markdown untuk QPlainTextEdit.

    Urutan aturan penting: aturan yang lebih spesifik didaftarkan lebih awal
    agar tidak tertimpa aturan umum (mis. bold+italic sebelum bold saja).
    Semua aturan bersifat per-baris kecuali fenced code block yang
    menggunakan block state antar baris.
    """

    # Block state
    _STATE_NORMAL    = 0
    _STATE_CODE_FENCE = 1      # di dalam ``` ... ```
    _STATE_CODE_INDENT = 2     # belum dipakai, placeholder

    def __init__(self, document: QTextDocument, palette: dict | None = None) -> None:
        super().__init__(document)
        self._palette = palette or {}
        self._rules:         list[tuple[re.Pattern, QTextCharFormat]] = []
        self._setext_rules:  list[tuple[re.Pattern, QTextCharFormat]] = []
        self._code_fence_fmt = QTextCharFormat()
        self._build_rules()

    def set_palette(self, palette: dict) -> None:
        self._palette = palette
        self._build_rules()
        self.rehighlight()

    # ── Format helpers ────────────────────────────────────────────────

    @staticmethod
    def _make_format(
        color: str | None = None,
        bg: str | None = None,
        bold: bool = False,
        italic: bool = False,
        size_pt: float | None = None,
        underline: bool = False,
    ) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        if bg:
            fmt.setBackground(QColor(bg))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        if size_pt:
            fmt.setFontPointSize(size_pt)
        if underline:
            fmt.setFontUnderline(True)
        return fmt

    # ── Rule builder ──────────────────────────────────────────────────

    def _build_rules(self) -> None:
        self._rules = []
        add = self._rules.append
        p = self._palette

        # Fallback if palette is empty
        def get_c(key, default):
            val = p.get(key, default)
            return val if isinstance(val, str) else val[0]

        def get_bg(key, default):
            val = p.get(key, default)
            return val[1] if isinstance(val, tuple) else default

        h_color = get_c("heading", "#1a1a2e")
        bi_color = get_c("bold_italic", "#111111")
        it_color = get_c("italic", "#444444")
        lnk_color = get_c("link", "#185FA5")
        lst_color = get_c("list", "#BA7517")
        esc_color = get_c("escape", "#c0392b")

        # ── Heading ATX (#) ───────────────────────────────────────────
        add((re.compile(r'^# .+'),   self._make_format(color=h_color, bold=True, size_pt=18)))
        add((re.compile(r'^## .+'),  self._make_format(color=h_color, bold=True, size_pt=16)))
        add((re.compile(r'^### .+'), self._make_format(color=h_color, bold=True, size_pt=14)))
        add((re.compile(r'^#{4} .+'),self._make_format(color=h_color, bold=True, size_pt=13)))
        add((re.compile(r'^#{5} .+'),self._make_format(color=h_color, bold=True)))
        add((re.compile(r'^#{6} .+'),self._make_format(color=h_color, bold=True)))

        # ── Heading Setext (=== dan ---) ───────────────────────────────
        self._setext_rules = [
            (re.compile(r'^={2,}\s*$'), self._make_format(color=h_color, bold=True)),
            (re.compile(r'^-{2,}\s*$'), self._make_format(color=h_color, bold=True)),
        ]

        # ── Bold + Italic ─────────────────────────────────────────────
        add((re.compile(r'\*{3}[^*\n]+\*{3}'),    self._make_format(bold=True, italic=True, color=bi_color)))
        add((re.compile(r'_{3}[^_\n]+_{3}'),      self._make_format(bold=True, italic=True, color=bi_color)))
        add((re.compile(r'\*\*_[^_\n]+_\*\*'),    self._make_format(bold=True, italic=True, color=bi_color)))
        add((re.compile(r'__\*[^*\n]+\*__'),       self._make_format(bold=True, italic=True, color=bi_color)))

        # ── Bold ──────────────────────────────────────────────────────
        add((re.compile(r'\*\*[^*\n]+\*\*'), self._make_format(bold=True)))
        add((re.compile(r'__[^_\n]+__'),      self._make_format(bold=True)))

        # ── Italic ────────────────────────────────────────────────────
        add((re.compile(r'\*[^*\n]+\*'), self._make_format(italic=True, color=it_color)))
        add((re.compile(r'_[^_\n]+_'),   self._make_format(italic=True, color=it_color)))

        # ── Image ─────────────────────────────────────────────────────
        img_fg, img_bg = p.get("image", ("#c77700", "#FFF8E1"))
        add((re.compile(r'!\[[^\]]*\]\([^\)]*\)'),
            self._make_format(color=img_fg, bg=img_bg)))

        # ── Link ──────────────────────────────────────────────────────
        add((re.compile(r'\[([^\]]+)\]\([^\)]+\)'),
            self._make_format(color=lnk_color, underline=True)))

        # ── Autolink ──────────────────────────────────────────────────
        add((re.compile(r'<(?:https?|ftp|mailto):[^>]+>'),
            self._make_format(color=lnk_color, underline=True)))
        add((re.compile(r'<[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}>'),
            self._make_format(color=lnk_color, underline=True)))

        # ── Wiki-link [[target]] ──────────────────────────────────────
        wiki_fg, wiki_bg = p.get("wiki", ("#534AB7", "#EEEDFE"))
        add((re.compile(r'\[\[[^\]]+\]\]'),
            self._make_format(color=wiki_fg, bg=wiki_bg)))

        # ── Citation @key ─────────────────────────────────────────────
        cite_fg, cite_bg = p.get("citation", ("#0F6E56", "#E1F5EE"))
        add((re.compile(r'@[A-Za-z][A-Za-z0-9_:\-]+'),
            self._make_format(color=cite_fg, bg=cite_bg)))

        # ── Inline code `code` ────────────────────────────────────────
        code_fg, code_bg = p.get("code", ("#1D9E75", "#F0FFF8"))
        add((re.compile(r'``[^`\n]+``'), self._make_format(color=code_fg, bg=code_bg)))
        add((re.compile(r'`[^`\n]+`'),   self._make_format(color=code_fg, bg=code_bg)))

        # ── Blockquote ────────────────────────────────────────────────
        quote_fg, quote_bg = p.get("quote", ("#888", "#FAFAFA"))
        add((re.compile(r'^>>+.*'),  self._make_format(color=quote_fg, italic=True, bg=quote_bg)))
        add((re.compile(r'^>.*'),    self._make_format(color=quote_fg, italic=True, bg=quote_bg)))

        # ── List ──────────────────────────────────────────────────────
        add((re.compile(r'^(\s*)[-*+] '),
            self._make_format(color=lst_color, bold=True)))
        add((re.compile(r'^(\s*)\d+[.)]\s'),
            self._make_format(color=lst_color, bold=True)))

        # ── Code block ────────────────────────────────────────────────
        cb_fg, cb_bg = p.get("code_block", ("#888", "#F5F5F5"))
        self._code_fence_fmt = self._make_format(color=cb_fg, bg=cb_bg)
        add((re.compile(r'^(?:    |\t).+'), self._code_fence_fmt))

        # ── Others ────────────────────────────────────────────────────
        add((re.compile(r'^\s*(\*{3,}|-{3,}|_{3,})\s*$'), self._make_format(color="#bbb")))
        add((re.compile(r'</?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?>'), self._make_format(color="#9b59b6")))
        add((re.compile(r'\\[\\`*_{}\[\]<>()+\-\.!|#]'), self._make_format(color=esc_color, bold=True)))
        add((re.compile(r'  +$'), self._make_format(bg="#D6EAF8", underline=True)))
        add((re.compile(r'^---\s*$'), self._make_format(color="#aaa")))

    # ── highlightBlock ────────────────────────────────────────────────

    def highlightBlock(self, text: str) -> None:
        prev_state = self.previousBlockState()

        # ── Fenced code block (``` ... ```) ───────────────────────────
        stripped = text.strip()
        if stripped.startswith("```"):
            entering = prev_state != self._STATE_CODE_FENCE
            self.setFormat(0, len(text), self._code_fence_fmt)
            # Toggle: jika masuk, set state CODE; jika keluar, set NORMAL
            self.setCurrentBlockState(
                self._STATE_CODE_FENCE if entering else self._STATE_NORMAL
            )
            return

        if prev_state == self._STATE_CODE_FENCE:
            self.setFormat(0, len(text), self._code_fence_fmt)
            self.setCurrentBlockState(self._STATE_CODE_FENCE)
            return

        self.setCurrentBlockState(self._STATE_NORMAL)

        # ── Setext heading underline (=== atau ---) ───────────────────
        # Periksa setelah keluar dari code block
        for pattern, fmt in self._setext_rules:
            if pattern.match(text):
                self.setFormat(0, len(text), fmt)
                return   # baris ini selesai

        # ── Terapkan semua aturan inline ──────────────────────────────
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
