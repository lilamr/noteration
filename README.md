<p align="center">
  <img src="assets/icon_256.png" width="96" alt="Noteration icon"/>
</p>

<h1 align="center">Noteration: Note-Literature-Synchronization</h1>

<p align="center">
  <strong>Research Literature Note-Taking App</strong><br>
  Markdown editor · PDF viewer · Papis · GitHub sync
</p>

<p align="center">
  <a href="https://github.com/lilamr/noteration/releases"><img src="https://img.shields.io/github/v/release/lilamr/noteration?label=versi&color=4CAF50" alt="Release"/></a>
  <a href="https://github.com/lilamr/noteration/blob/main/LICENSE"><img src="https://img.shields.io/badge/lisensi-MIT-blue" alt="License"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python"/></a>
  <a href="https://github.com/lilamr/noteration/actions"><img src="https://img.shields.io/github/actions/workflow/status/lilamr/noteration/ci.yml?label=CI" alt="CI"/></a>
</p>

---

## Tentang

Noteration adalah aplikasi desktop untuk mengelola catatan literatur secara terintegrasi. Menyatukan semua alat yang dibutuhkan dalam satu antarmuka:

```
noteration/
├── 📄  Markdown notes dengan [[wiki-link]] dan @citation
├── 📘  PDF viewer terintegrasi dengan anotasi non-destructive
├── 📚  Browser literatur via Papis
├── 🔍  Pencarian global vault
├── 🕸️  Backlink graph interaktif antar catatan
└── ☁️  Sinkronisasi otomatis via GitHub
```

---

## Fitur Unggulan

| Fitur | Keterangan |
|-------|------------|
| **Editor Markdown** | Syntax highlighting, line numbers, mode view/edit, auto-indent |
| **Wiki-link** | `[[nama-catatan]]` dengan navigasi `Ctrl+Klik` dan autocomplete |
| **Citation** | `@citation-key` dengan autocomplete dari library Papis |
| **Pencarian Global** | Cari di seluruh catatan, literatur, dan anotasi PDF sekaligus |
| **PDF Viewer** | Render via QtPDF atau PyMuPDF, highlight & anotasi JSON |
| **Backlink Graph** | Visualisasi jaringan antar catatan, interaktif |
| **Papis Bridge** | Browse, import, dan export BibTeX dari library Papis |
| **Git Sync** | Commit, pull, push otomatis; resolusi konflik visual |
| **Dark Mode** | Light / Dark / System — mengikuti tema OS secara otomatis |

---

## Instalasi

```bash
# Clone repositori
git clone https://github.com/lilamr/noteration.git
cd noteration

# Install dependensi dasar
pip install -e .

# Install semua fitur opsional sekaligus
pip install -e ".[all]"
```

### Dependensi opsional

| Fitur | Perintah |
|-------|----------|
| Manajemen literatur Papis | `pip install -e ".[papis]"` |
| PDF renderer PyMuPDF | `pip install -e ".[pymupdf]"` |
| Fuzzy search | `pip install -e ".[search]"` |
| Backlink graph (NetworkX) | `pip install -e ".[graph]"` |
| File watcher (live reload) | `pip install -e ".[watch]"` |
| Markdown preview | `pip install -e ".[markdown]"` |

> **Catatan:** Python 3.11+ diperlukan. PySide6 ≥ 6.4 sudah mencakup QtPDF bawaan.

---

## Menjalankan Aplikasi

```bash
# Via entry point (setelah pip install -e .)
noteration

# Atau langsung sebagai modul
python -m noteration
```

Saat pertama kali dijalankan, dialog **Pilih Vault** akan muncul untuk memilih atau membuat vault penelitian baru.

---

## Struktur Vault

```
~/noteration-vault/
├── .noteration/
│   ├── config.toml          # Konfigurasi utama
│   ├── db.sqlite            # Cache & link graph
│   └── link_graph.json      # Graf backlink (JSON)
├── notes/                   # File Markdown
│   ├── index.md
│   └── topik-penelitian.md
├── literature/              # Dikelola Papis
├── annotations/             # Anotasi PDF (JSON, disinkronkan via Git)
└── attachments/             # Gambar dan lampiran
```

---

## Konfigurasi (`config.toml`)

```toml
[general]
autosave          = true
autosave_interval = 30           # detik

[editor]
tab_width         = 2
font_family       = "Consolas"
font_size         = 12
show_line_numbers = true
auto_indent       = true

[pdf]
renderer              = "qtpdf"   # atau "pymupdf"
default_highlight_color = "#FFEB3B"

[papis]
library_path = "~/noteration/literature"

[sync]
auto_sync     = true
sync_interval = 300              # detik
remote        = "origin"
branch        = "main"

[ui]
theme           = "system"       # dark / light / system
sidebar_visible = true
```

---

## Struktur Proyek

```
noteration/
├── assets/
├── noteration/
│   ├── app.py               # Bootstrap & QApplication
│   ├── config.py            # Konfigurasi TOML
│   ├── db/                  # Link graph & layout engine
│   ├── dialogs/             # Dialog (vault, note, settings, konflik)
│   ├── editor/              # Find/Replace, syntax highlight, wiki-link
│   ├── literature/          # Papis bridge & BibTeX export
│   ├── pdf/                 # PDF reader & anotasi
│   ├── search/              # Pencarian global vault
│   ├── sync/                # Git engine
│   └── ui/                  # Jendela utama, tab, sidebar, graph
├── tests/                   # Pytest test suite
├── docs/
│   └── user_guide.md
└── pyproject.toml
```

---

## Kontribusi

Kontribusi sangat disambut! Lihat [Issues](https://github.com/lilamr/noteration/issues) untuk daftar hal yang sedang dikerjakan, atau buka issue baru untuk melaporkan bug atau mengusulkan fitur.

```bash
# Setup lingkungan pengembangan
pip install -e ".[all,dev]"

# Jalankan test
pytest

# Linting
ruff check noteration/
```

---

## Penulis

Dibuat oleh **[lilamr](https://github.com/lilamr)**.

---

## Lisensi

[MIT License](LICENSE) — bebas digunakan, dimodifikasi, dan didistribusikan.

---

<p align="center">
  Dibuat dengan PySide6 · PyMuPDF · GitPython · NetworkX · Papis
</p>
