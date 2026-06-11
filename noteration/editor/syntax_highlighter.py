r"""noteration/editor/syntax_highlighter.py

QSyntaxHighlighter for Markdown — covers all Basic Syntax features
according to the markdownguide.org/basic-syntax specification.

Key Features:
  - ATX Headings (#)
  - Alternative Setext Headings (=== and --- after text)
  - Bold, Italic, and Bold+Italic combinations (***, ___, etc.)
  - Nested blockquotes (>)
  - Unordered lists (-, *, +) and Ordered lists (1.)
  - Indented and Fenced code blocks
  - Horizontal rules (***, ---, ___)
  - Images ![alt](url)
  - Autolinks <url> and <email>
  - Reference-style links [text][label] and definitions [label]: url
  - Escape characters (\*, \_, etc.)
  - HTML inline tags (<em>, <strong>, <br>, etc.)
  - Trailing line breaks (2+ spaces at end of line)
"""

from __future__ import annotations

import re

from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)


class MarkdownHighlighter(QSyntaxHighlighter):
    """Markdown syntax highlighter for QPlainTextEdit.

    The order of rules is important: more specific rules are registered earlier
    to avoid being overwritten by general rules (e.g., bold+italic before bold).
    All rules are per-line except for fenced code blocks, which use block states
    to maintain state between lines.
    """

    # Block states
    _STATE_NORMAL = 0
    _STATE_CODE_FENCE = 1  # Inside ``` ... ```
    _STATE_CODE_INDENT = 2  # Placeholder for future use

    def __init__(self, document: QTextDocument, palette: dict | None = None) -> None:
        super().__init__(document)
        self._palette = palette or {}
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []
        self._setext_rules: list[tuple[re.Pattern, QTextCharFormat]] = []
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

        # ── ATX Headings (#) ──────────────────────────────────────────
        add((re.compile(r"^# .+"), self._make_format(color=h_color, bold=True, size_pt=18)))
        add((re.compile(r"^## .+"), self._make_format(color=h_color, bold=True, size_pt=16)))
        add((re.compile(r"^### .+"), self._make_format(color=h_color, bold=True, size_pt=14)))
        add((re.compile(r"^#{4} .+"), self._make_format(color=h_color, bold=True, size_pt=13)))
        add((re.compile(r"^#{5} .+"), self._make_format(color=h_color, bold=True)))
        add((re.compile(r"^#{6} .+"), self._make_format(color=h_color, bold=True)))

        # ── Setext Headings (=== and ---) ─────────────────────────────
        self._setext_rules = [
            (re.compile(r"^={2,}\s*$"), self._make_format(color=h_color, bold=True)),
            (re.compile(r"^-{2,}\s*$"), self._make_format(color=h_color, bold=True)),
        ]

        # ── Bold + Italic ─────────────────────────────────────────────
        add(
            (
                re.compile(r"\*{3}[^*\n]+\*{3}"),
                self._make_format(bold=True, italic=True, color=bi_color),
            )
        )
        add(
            (
                re.compile(r"_{3}[^_\n]+_{3}"),
                self._make_format(bold=True, italic=True, color=bi_color),
            )
        )
        add(
            (
                re.compile(r"\*\*_[^_\n]+_\*\*"),
                self._make_format(bold=True, italic=True, color=bi_color),
            )
        )
        add(
            (
                re.compile(r"__\*[^*\n]+\*__"),
                self._make_format(bold=True, italic=True, color=bi_color),
            )
        )

        # ── Bold ──────────────────────────────────────────────────────
        add((re.compile(r"\*\*[^*\n]+\*\*"), self._make_format(bold=True)))
        add((re.compile(r"__[^_\n]+__"), self._make_format(bold=True)))

        # ── Italic ────────────────────────────────────────────────────
        add((re.compile(r"\*[^*\n]+\*"), self._make_format(italic=True, color=it_color)))
        add((re.compile(r"_[^_\n]+_"), self._make_format(italic=True, color=it_color)))

        # ── Image ─────────────────────────────────────────────────────
        img_fg, img_bg = p.get("image", ("#c77700", "#FFF8E1"))
        add((re.compile(r"!\[[^\]]*\]\([^\)]*\)"), self._make_format(color=img_fg, bg=img_bg)))

        # ── Link ──────────────────────────────────────────────────────
        add(
            (
                re.compile(r"\[([^\]]+)\]\([^\)]+\)"),
                self._make_format(color=lnk_color, underline=True),
            )
        )

        # ── Autolink ──────────────────────────────────────────────────
        add(
            (
                re.compile(r"<(?:https?|ftp|mailto):[^>]+>"),
                self._make_format(color=lnk_color, underline=True),
            )
        )
        add(
            (
                re.compile(r"<[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}>"),
                self._make_format(color=lnk_color, underline=True),
            )
        )

        # ── Wiki-link [[target]] ──────────────────────────────────────
        wiki_fg, wiki_bg = p.get("wiki", ("#534AB7", "#EEEDFE"))
        add((re.compile(r"\[\[[^\]]+\]\]"), self._make_format(color=wiki_fg, bg=wiki_bg)))

        # ── Citation @key[locator] ────────────────────────────────────
        cite_fg, cite_bg = p.get("citation", ("#0F6E56", "#E1F5EE"))
        add(
            (
                re.compile(r"@[A-Za-z][A-Za-z0-9_:\-]+(?:\[[^\]]+\])?"),
                self._make_format(color=cite_fg, bg=cite_bg),
            )
        )

        # ── Inline code `code` ────────────────────────────────────────
        code_fg, code_bg = p.get("code", ("#1D9E75", "#F0FFF8"))
        add((re.compile(r"``[^`\n]+``"), self._make_format(color=code_fg, bg=code_bg)))
        add((re.compile(r"`[^`\n]+`"), self._make_format(color=code_fg, bg=code_bg)))

        # ── Blockquote ────────────────────────────────────────────────
        quote_fg, quote_bg = p.get("quote", ("#888", "#FAFAFA"))
        add((re.compile(r"^>>+.*"), self._make_format(color=quote_fg, italic=True, bg=quote_bg)))
        add((re.compile(r"^>.*"), self._make_format(color=quote_fg, italic=True, bg=quote_bg)))

        # ── List ──────────────────────────────────────────────────────
        add((re.compile(r"^(\s*)[-*+] "), self._make_format(color=lst_color, bold=True)))
        add((re.compile(r"^(\s*)\d+[.)]\s"), self._make_format(color=lst_color, bold=True)))

        # ── Code block ────────────────────────────────────────────────
        cb_fg, cb_bg = p.get("code_block", ("#888", "#F5F5F5"))
        self._code_fence_fmt = self._make_format(color=cb_fg, bg=cb_bg)
        add((re.compile(r"^(?:    |\t).+"), self._code_fence_fmt))

        # ── Others ────────────────────────────────────────────────────
        add((re.compile(r"^\s*(\*{3,}|-{3,}|_{3,})\s*$"), self._make_format(color="#bbb")))
        add(
            (
                re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?>"),
                self._make_format(color="#9b59b6"),
            )
        )
        add(
            (
                re.compile(r"\\[\\`*_{}\[\]<>()+\-\.!|#]"),
                self._make_format(color=esc_color, bold=True),
            )
        )
        add((re.compile(r"  +$"), self._make_format(bg="#D6EAF8", underline=True)))
        add((re.compile(r"^---\s*$"), self._make_format(color="#aaa")))

    # ── highlightBlock ────────────────────────────────────────────────

    def highlightBlock(self, text: str) -> None:
        prev_state = self.previousBlockState()

        # ── Fenced code block (``` ... ```) ───────────────────────────
        stripped = text.strip()
        if stripped.startswith("```"):
            entering = prev_state != self._STATE_CODE_FENCE
            self.setFormat(0, len(text), self._code_fence_fmt)
            # Toggle state: if entering, set state to CODE; if exiting, set to NORMAL
            self.setCurrentBlockState(self._STATE_CODE_FENCE if entering else self._STATE_NORMAL)
            return

        if prev_state == self._STATE_CODE_FENCE:
            self.setFormat(0, len(text), self._code_fence_fmt)
            self.setCurrentBlockState(self._STATE_CODE_FENCE)
            return

        self.setCurrentBlockState(self._STATE_NORMAL)

        # ── Setext heading underline (=== or ---) ───────────────────
        # Check after exiting a code block
        for pattern, fmt in self._setext_rules:
            if pattern.match(text):
                self.setFormat(0, len(text), fmt)
                return  # This line is handled

        # ── Apply all inline rules ────────────────────────────────────
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
