"""noteration/ui/editor/markdown_preview.py

Preview component for rendered Markdown.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from noteration.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from noteration.vault_manager import VaultManager

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False

try:
    import markdown as _markdown_lib  # type: ignore[import-untyped]

    _HAS_MARKDOWN = True
except ImportError:
    _HAS_MARKDOWN = False

# Default CSS for the rendered HTML view
_PREVIEW_CSS = """
:root {
  --bg:      #ffffff;
  --text:    #24292e;
  --muted:   #6a737d;
  --border:  #e1e4e8;
  --code-bg: #f6f8fa;
  --link:    #0366d6;
  --bq-border: #dfe2e5;
  --bq-bg:   #f9f9f9;
  --hl-bg:   #fff3cd;
  --wiki-bg: #EEEDFE;
  --wiki-fg: #534AB7;
  --cite-bg: #E1F5EE;
  --cite-fg: #0F6E56;
}
* { box-sizing: border-box; }
html { font-size: 16px; background: var(--bg); }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
               Helvetica, Arial, sans-serif;
  font-size: 1rem;
  line-height: 1.7;
  color: var(--text);
  background: var(--bg);
  max-width: 780px;
  margin: 0 auto;
  padding: 2rem 2.5rem 4rem;
}
/* Headings */
h1,h2,h3,h4,h5,h6 {
  font-weight: 600;
  line-height: 1.25;
  margin-top: 1.5em;
  margin-bottom: .5em;
}
h1 { font-size: 2em;   border-bottom: 1px solid var(--border); padding-bottom:.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid var(--border); padding-bottom:.3em; }
h3 { font-size: 1.25em; }
h4 { font-size: 1em; }
h5 { font-size: .875em; }
h6 { font-size: .85em;  color: var(--muted); }
p { margin: 0 0 1em; }
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
strong { font-weight: 600; }
blockquote {
  margin: 1em 0;
  padding: .5em 1em;
  color: var(--muted);
  background: var(--bq-bg);
  border-left: .25em solid var(--bq-border);
  border-radius: 0 4px 4px 0;
}
blockquote p { margin: 0; }
ul, ol { padding-left: 2em; margin: 0 0 1em; }
li + li { margin-top: .25em; }
code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: .9em;
  background: var(--code-bg);
  padding: .1em .35em;
  border-radius: 3px;
  border: 1px solid var(--border);
}
pre {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1em 1.25em;
  overflow-x: auto;
  line-height: 1.5;
  margin: 0 0 1em;
}
pre code {
  background: transparent;
  border: none;
  padding: 0;
  font-size: .875em;
}
hr {
  border: none;
  border-top: 2px solid var(--border);
  margin: 1.5em 0;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 1em;
  font-size: .9em;
}
th, td {
  border: 1px solid var(--border);
  padding: .5em .75em;
  text-align: left;
}
th { background: var(--code-bg); font-weight: 600; }
tr:nth-child(even) { background: var(--bq-bg); }
img { max-width: 100%; height: auto; border-radius: 4px; }
a.wikilink {
  background: var(--wiki-bg);
  color: var(--wiki-fg);
  padding: .05em .35em;
  border-radius: 3px;
  font-size: .9em;
  text-decoration: none;
  border: 1px solid var(--border);
  cursor: pointer;
}
a.wikilink:hover {
  opacity: 0.8;
}
.citation {
  background: var(--cite-bg);
  color: var(--cite-fg);
  padding: .05em .3em;
  border-radius: 3px;
  font-size: .9em;
  font-family: monospace;
}
"""

_MARKDOWN_EXTENSIONS = [
    "pymdownx.arithmatex",
    "pymdownx.superfences",
    "pymdownx.tasklist",
    "pymdownx.tilde",
    "pymdownx.caret",
    "pymdownx.mark",
    "extra",
    "sane_lists",
    "toc",
]

_EXTENSION_CONFIGS = {
    "pymdownx.arithmatex": {
        "generic": True,
        "smart_dollar": True,
    }
}


def _md_to_html(
    text: str, base_url: str = "", theme: str = "light", vault: "VaultManager" | None = None
) -> str:
    """Convert Markdown content to a self-contained HTML document.
    Handles wiki-links, citations, and theme-specific syntax coloring.
    """
    import re

    from PySide6.QtGui import QPalette

    from noteration.ui.theme import (
        _DARK_COLORS,
        _LIGHT_COLORS,
        ThemeMode,
        get_effective_mode,
        get_syntax_palette,
    )

    mode = get_effective_mode(theme)
    syntax = get_syntax_palette(mode)
    base = _DARK_COLORS if mode == ThemeMode.DARK else _LIGHT_COLORS

    # Helper to get syntax colors (can be str or tuple)
    def get_syntax_bg(key, default):
        val = syntax.get(key, default)
        return val[1] if isinstance(val, tuple) else val

    def get_syntax_fg(key, default):
        val = syntax.get(key, default)
        return val[0] if isinstance(val, tuple) else val

    # 1. Wiki-links [[target]] or [[target|label]]
    # Simplified: convert to <a class="wikilink" href="noteration://wiki/target">label</a>
    def replace_wiki(match):
        target = match.group(1).strip()
        label = match.group(3).strip() if match.group(3) else target
        # URL encode target for safety
        from urllib.parse import quote
        safe_target = quote(target)
        return f'<a class="wikilink" href="noteration://wiki/{safe_target}">{label}</a>'

    # Pattern for [[Target|Label]] or [[Target]]
    wiki_pattern = re.compile(r"\[\[([^|\]]+)(\|([^\]]+))?\]\]")
    text = wiki_pattern.sub(replace_wiki, text)

    # 2. Citations [@key] or @key
    def replace_cite(match):
        key = match.group(1)
        # Check if we have literature data to show a tooltip
        title = ""
        if vault and vault.papis:
            entry = vault.papis.get(key)
            if entry:
                title = entry.title or key

        tooltip = f' title="{title}"' if title else ""
        return f'<span class="citation"{tooltip}>@{key}</span>'

    cite_pattern = re.compile(r"\[?@([a-zA-Z0-9_.-]+)\]?")
    text = cite_pattern.sub(replace_cite, text)

    # 4. Render Markdown
    if _HAS_MARKDOWN:
        body = _markdown_lib.markdown(
            text, extensions=_MARKDOWN_EXTENSIONS, extension_configs=_EXTENSION_CONFIGS
        )
    else:
        body = f"<pre>{text}</pre>"

    # 5. Assemble full document with CSS variables for theming
    css_vars = f"""
  --bg:      {base[QPalette.ColorRole.Base]};
  --text:    {base[QPalette.ColorRole.Text]};
  --muted:   {base[QPalette.ColorRole.PlaceholderText]};
  --border:  {base[QPalette.ColorRole.Mid]};
  --code-bg: {get_syntax_bg('code', '#f6f8fa')};
  --link:    {base[QPalette.ColorRole.Link]};
  --bq-border: {base[QPalette.ColorRole.Dark]};
  --bq-bg:   {get_syntax_bg('quote', '#f9f9f9')};
  --wiki-bg: {get_syntax_bg('wiki', '#EEEDFE')};
  --wiki-fg: {get_syntax_fg('wiki', '#534AB7')};
  --cite-bg: {get_syntax_bg('citation', '#E1F5EE')};
  --cite-fg: {get_syntax_fg('citation', '#0F6E56')};
    """

    mathjax_url = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"
    base_tag = f'<base href="{base_url}">' if base_url else ""

    html_template = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  %BASE_TAG%
  <style>
    %STYLE%
    :root { %CSS_VARS% }
  </style>
  <script>
    window.MathJax = {
      tex: {
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
        processEscapes: true
      },
      options: {
        processHtmlClass: 'arithmatex',
        enableMenu: false
      }
    };
  </script>
  <script src="%MATHJAX_URL%"></script>
</head>
<body>
<div class="markdown-body">
%BODY%
</div>
</body>
</html>"""
    return (
        html_template.replace("%BASE_TAG%", base_tag)
        .replace("%STYLE%", _PREVIEW_CSS)
        .replace("%CSS_VARS%", css_vars)
        .replace("%MATHJAX_URL%", mathjax_url)
        .replace("%BODY%", body)
    )


if _HAS_WEBENGINE:

    class _NoterationPage(QWebEnginePage):
        """Intercept navigation requests to handle wiki-links and external URLs.
        """

        link_clicked = Signal(str)

        def acceptNavigationRequest(
            self,
            url: QUrl | str,
            nav_type: QWebEnginePage.NavigationType,
            is_main_frame: bool,
        ) -> bool:
            from PySide6.QtCore import QUrl as QUrlClass

            if isinstance(url, str):
                url = QUrlClass(url)
            scheme = url.scheme()

            if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                return True

            if scheme == "noteration":
                if url.host() == "wiki":
                    target = url.path().lstrip("/")
                    # Decode target
                    from urllib.parse import unquote
                    target = unquote(target)
                    self.link_clicked.emit(target)
                return False

            if scheme in ("http", "https", "ftp"):
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(url)
                return False

            return False


class MarkdownPreview(QWidget):
    """Preview component for rendered Markdown.
    Uses QWebEngineView for rich rendering or QTextBrowser as a fallback.
    """

    link_clicked = Signal(str)
    export_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Allow forced fallback for compatibility
        force_text = os.environ.get("NOTERATION_USE_TEXT_BROWSER") == "1"

        if _HAS_WEBENGINE and not force_text:
            self._view = QWebEngineView()
            self._page = _NoterationPage(self)
            self._page.link_clicked.connect(self.link_clicked)

            # Security: Allow local content to access local file URLs for MathJax and images
            settings = self._page.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )  # Required for MathJax

            self._view.setPage(self._page)
            self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._view.customContextMenuRequested.connect(self._handle_context_menu)
            self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self._view)
            self._use_webengine = True
        else:
            from PySide6.QtWidgets import QTextBrowser

            self._tb = QTextBrowser()
            self._tb.setOpenExternalLinks(False)
            self._tb.setOpenLinks(False)
            self._tb.anchorClicked.connect(self._on_tb_anchor)
            self._tb.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._tb.customContextMenuRequested.connect(self._handle_context_menu)
            self._tb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self._tb)
            self._use_webengine = False

    def _handle_context_menu(self, pos) -> None:
        """View-mode context menu with export options."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)

        copy = menu.addAction("Copy")
        menu.addSeparator()

        export_menu = menu.addMenu("📥 Export")
        export_html = export_menu.addAction("HTML")
        export_pdf = export_menu.addAction("PDF")
        export_docx = export_menu.addAction("DOCX")
        export_odt = export_menu.addAction("ODT")
        export_latex = export_menu.addAction("LaTeX")
        export_txt = export_menu.addAction("Plain Text (TXT)")

        sender_obj = self.sender()
        sender = (
            sender_obj
            if isinstance(sender_obj, QWidget)
            else (self._view if self._use_webengine else self._tb)
        )

        chosen = menu.exec(sender.mapToGlobal(pos))
        if not chosen:
            return

        if chosen == copy:
            if self._use_webengine:
                self._view.triggerPageAction(QWebEnginePage.WebAction.Copy)
            else:
                self._tb.copy()
        elif chosen in [export_html, export_pdf, export_txt, export_docx, export_odt, export_latex]:
            if chosen == export_html:
                fmt = "html"
            elif chosen == export_pdf:
                fmt = "pdf"
            elif chosen == export_txt:
                fmt = "txt"
            elif chosen == export_docx:
                fmt = "docx"
            elif chosen == export_odt:
                fmt = "odt"
            else:
                fmt = "latex"

            self.export_requested.emit(fmt)

    def _on_tb_anchor(self, url: QUrl) -> None:
        """Handle link clicks in the fallback text browser."""
        scheme = url.scheme()
        if scheme == "noteration" and url.host() == "wiki":
            self.link_clicked.emit(url.path().lstrip("/"))
        elif scheme in ("http", "https"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)

    def shutdown(self) -> None:
        """Explicitly cleanup WebEngine resources to avoid profile release warnings."""
        if self._use_webengine:
            # 0. Ensure Qt application is still active before GUI cleanup.
            from PySide6.QtWidgets import QApplication
            if not QApplication.instance():
                return

            # 1. Detach and hide the view
            if hasattr(self, "_view") and self._view:
                self._view.hide()
                self._view.setPage(None)  # type: ignore[arg-type]

            # 2. Forcefully delete the page first
            if hasattr(self, "_page") and self._page:
                self._page.setParent(None)
                try:
                    self._page.deleteLater()
                except Exception as e:
                    logger.debug(f"Shiboken delete _page failed: {e}")
                self._page = None  # type: ignore

            # 3. Forcefully delete the view
            if hasattr(self, "_view") and self._view:
                self._view.setParent(None)
                try:
                    self._view.deleteLater()
                except Exception as e:
                    logger.debug(f"Shiboken delete _view failed: {e}")
                self._view = None  # type: ignore

    def set_content(
        self,
        markdown_text: str,
        base_path: Optional[Path] = None,
        theme: str = "light",
        vault: Optional["VaultManager"] = None,
    ) -> None:
        """Update the displayed content."""
        base_url = QUrl()
        if base_path and base_path.exists():
            base_dir = str(base_path) if base_path.is_dir() else str(base_path.parent)
            if not base_dir.endswith("/"):
                base_dir += "/"
            base_url = QUrl.fromLocalFile(base_dir)

        html = _md_to_html(markdown_text, base_url.toString(), theme=theme, vault=vault)

        if self._use_webengine:
            self._page.setHtml(html, base_url)
        else:
            self._tb.setHtml(html)
