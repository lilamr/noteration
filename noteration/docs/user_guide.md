# Noteration User Guide

**Noteration** is a desktop application for managing literature notes in an integrated way. It combines a Markdown editor, PDF viewer, Papis literature management, and Git synchronization in a single interface.

---

## Table of Contents

1. [Getting Started — Vault](#1-getting-started--vault)
2. [Main Interface](#2-main-interface)
3. [Markdown Editor](#3-markdown-editor)
4. [Wiki-links between Notes](#4-wiki-links-between-notes)
5. [Citations and @citation Autocomplete](#5-citations-and-citation-autocomplete)
6. [Global Vault Search](#6-global-vault-search)
7. [PDF Viewer and Annotations](#7-pdf-viewer-and-annotations)
8. [Literature Management (Papis)](#8-literature-management-papis)
9. [Backlink Graph](#9-backlink-graph)
10. [Git Synchronization](#10-git-synchronization)
11. [Settings](#11-settings)
12. [Full Shortcuts](#12-full-shortcuts)
13. [Focus Mode & Vim Keybindings](#13-focus-mode--vim-keybindings)
14. [`config.toml` Configuration](#14-configtoml-configuration)
15. [Vault Structure](#15-vault-structure)
16. [Frequently Asked Questions (FAQ)](#16-frequently-asked-questions-faq)

---

## 1. Getting Started — Vault

Noteration works based on **Vaults**: a folder that serves as your main project directory. It is the hub for all your notes, literature, annotations, and attachments.

### Creating a New Vault

1. Run Noteration — the **Select Vault** dialog appears automatically.
2. Click **Create New Vault**.
3. Fill in the vault name and choose the folder location.
4. Click **Create** — the folder will be created along with its subfolder structure.

### Opening an Existing Vault

1. In the **Select Vault** dialog, choose a vault from the history list, or
2. Click **Open Folder…** to manually select a vault folder.

> **Tip:** You can open multiple vaults at once — each vault opens its own MainWindow via **File › Open Vault…**.

### Removing a Vault from the List

Right-click on a vault in the Select Vault dialog → **Remove from List**.
This only removes the entry from the history, not the folder itself.

---

## 2. Main Interface

```
┌─────────────────────────────────────────────────────────────────┐
│  Toolbar: + Note │ Save │ Literature │ Sync │ Search │ Git:     │
├──────────┬──────────────────────────────────────┬───────────────┤
│          │                                      │               │
│Navigator │         Main Tabs                    │  Backlinks    │
│          │  (Editor / PDF / Literature / Sync)   │  ──────────   │
│ ▾ NOTES  │                                      │  Graph        │
│  index   │                                      │               │
│  research│                                      │               │
│ ──────── │                                      │               │
│ ▾ OUTLINE│                                      │               │
│  # Sec 1 │                                      │               │
│ ──────── │                                      │               │
│ ▾ CITATIONS                                     │               │
│  @darwin │                                      │               │
│          │                                      │               │
├──────────┴──────────────────────────────────────┴───────────────┤
│ filename.md │ Ln 12, Col 5 │ 342 words │ ● synced │ vault       │
└─────────────────────────────────────────────────────────────────┘
```

### Left Panel — Navigator

The Navigator panel contains four collapsible/expandable sections:

| Section | Content |
|--------|-----|
| **Notes** | Markdown file/folder tree. Supports drag-and-drop. |
| **Related PDFs** | PDFs from the Papis library cited in the active note. Click to open. |
| **Outline** | List of headings (`#`, `##`, `###`) from the active note. Click to jump. |
| **Citations** | List of `@citation-keys` used in the active note. Click to jump. |

### Menu Bar

| Menu | Content |
|------|-----|
| **File** | New Note, Open Vault, Save, Exit |
| **View** | Toggle sidebar/right panel, Focus Mode, Literature, Synchronization |
| **Search** | Global vault search |
| **Tools** | Synchronize, Export BibTeX, Build Backlink Graph, Settings |
| **Help** | Guide, Research and Writing, About |

### Right Panel — Link Graph

Contains two tabs:

- **Backlinks**: list of other notes linking to the currently opened note.
- **Graph**: visualization of the entire vault's wiki-link network (see [§10](#9-backlink-graph)).

### Status Bar

| Indicator | Description |
|-----------|-----------|
| Filename | The currently active note. A `*` symbol means there are unsaved changes. |
| `Ln X, Col Y` | Cursor position (line and column). |
| `N words` | Word count in the active note (excluding front-matter and code). |
| `● synced` / `● modified` / `○ offline` | Git repository status. |
| Vault Name | The currently open vault. |

---

## 3. Markdown Editor

### Creating a New Note

- **Ctrl+N** or toolbar **+ Note** → name and folder dialog appears.
- Fill in the filename (without `.md`) and choose a subfolder if desired.
- Click **Create** — the file opens immediately in the editor.

### Saving

- **Ctrl+S** for manual save.
- Autosave runs automatically every 30 seconds (configurable in Settings).
- When closing an unsaved tab, the file is saved automatically.

### Edit Mode vs View Mode (Preview)

Each editor tab has two modes:

| Mode | Appearance | How to Switch |
|------|----------|--------------|
| **Edit** | Raw Markdown text with syntax highlighting | `Edit` button in tab toolbar |
| **View** | Rendered HTML from Markdown | `View` button in tab toolbar, or `Ctrl+Shift+V` |

- Right-click in edit mode for undo, redo, copy, cut, paste, select, find and replace.
- Right-click in view mode to export to HTML, TXT, or PDF.

### Supported Markdown Syntax

```markdown
# Heading 1
## Heading 2
### Heading 3

**bold**   _italic_   ~~strikethrough~~   `inline code`

- list item
1. numbered list

> blockquote

```python
# code block with syntax highlighting
def hello():
    print("Noteration!")
```

![Image](attachments/image.png)
[External Link](https://example.com)
```

### Pasting and Inserting Images

- **Drag & drop** an image file from file manager to the editor → image is copied automatically to `attachments/` and `![]()` syntax is inserted.
- **Paste** an image from the clipboard (Ctrl+V after screenshot) → same as drag & drop.

### Line Numbers and Active Line Highlighting

Line numbers are displayed on the left side of the editor. The currently active line is highlighted with a different color. Both can be disabled in **Settings › Editor**.

---

## 4. Wiki-links between Notes

Wiki-links are a way to connect notes with each other, similar to Obsidian or Roam.

### Syntax

```markdown
See [[note-name]] for more details.
Or with an alias: [[note-name|display text]]
```

### Navigation

- **Ctrl+Click** on `[[note-name]]` in the editor → opens that note.
- If the note doesn't exist yet, a dialog appears offering to **create a new note**.
- Click on a backlink in the right panel → opens the source note.

### Link Resolution

Noteration recursively searches for the file `note-name.md` within the `notes/` folder. Names are case-insensitive and ignore the `.md` extension.

### Drag-and-Drop in Navigator

Note files and folders can be moved and rearranged by drag-and-drop in the Navigator panel:

- Drag a file to a destination folder to move it.
- Drag to an empty area to move to the root `notes/`.
- If the name already exists at the destination, a confirmation dialog appears.
- Currently open tabs are updated automatically to follow the new path.

---

## 5. Citations and @citation Autocomplete

### How to Insert a Citation

In the editor, type `@` followed by a few letters of the title, author, or citation key:

```markdown
As explained by @darwin1859 in his theory of evolution...
```

A suggestions list appears automatically — select with arrow keys and `Enter`.

### Supported Citation Formats

| Format | Example |
|--------|--------|
| Single key | `@darwin1859` |
| With page | `@darwin1859[p. 42]` |
| Multiple citations | `@newton1687; @einstein1905` |

### Jumping to a Citation

In the Navigator panel's **Citations** section, click on a `@key` to jump directly to its occurrence in the note.

### Exporting BibTeX

- **Tools › Export BibTeX (all)** — export the entire library to a single `.bib` file.
- **Tools › Export BibTeX (this note)** — export only the citations used in the active note.

---

## 6. Global Vault Search

Open through the **Search** menu in the menu bar, or **Ctrl+F** (applies to the entire vault, regardless of the active tab).

### Search Scope

Global Search covers three sources simultaneously:

| Icon | Source | What is searched |
|------|--------|------------|
| 📄 | **Notes** | Content of all `.md` files in the `notes/` folder |
| 📚 | **Literature** | Title, author, abstract, and tags from the Papis library |
| 📌 | **Annotations** | Highlighted text and notes created in PDFs |

### How to Use

1. Type keywords — results appear automatically after a short delay.
2. Use **Case Sensitive** and **Regex** filters to refine your search.
3. Click a result to open: notes open in an editor tab, literature opens in the Literature tab, annotations open the PDF at the relevant page.

### Pre-fill from Selection

If text is selected in the editor when opening this dialog, that text automatically becomes the initial keyword. This dialog applies to vault-wide searches (notes, literature, and annotations).

---

## 7. PDF Viewer and Annotations

### Opening a PDF

- From the **Literature** tab: click the PDF button on a literature entry.
- From the **Related PDFs** panel in the sidebar.
- Drag & drop a PDF file into the Noteration window.

### PDF Navigation

| Action | How |
|------|------|
| Change page | Arrow buttons in viewer toolbar, or scroll |
| Zoom | `+` / `-` buttons in toolbar, or `Ctrl+Scroll` |
| Jump to page | Type the page number in the navigation field |

### Highlights and Annotations

1. Select text on a PDF page with the mouse.
2. An annotation panel appears on the right with options:
   - **Highlight** — highlight text with color (default yellow, configurable in Settings).
   - **Note** — add a text note to the selection.
   - **Insert text to editor** — insert the text as a blockquote in the active note editor, complete with an automatic `@citation-key`.
3. Use Image to highlight images from the PDF. The resulting images will be saved in the `annotations/images` folder within the vault.

### Annotation Storage (Non-Destructive)

Annotations **do not modify the original PDF file**. All annotations are saved in JSON format in the `annotations/` folder, named after the PDF file's SHA-256 hash:

```
annotations/
└── a3f8c2...d1b9.json   ← annotations for one PDF
```

This JSON file is synchronized via Git, so annotations can be shared or synced across devices.

---

## 8. Literature Management (Papis)

The Literature tab displays the contents of your [Papis](https://papis.io/) library.

### Adding New Entries

#### Via DOI

1. Click **+ Add via DOI** in the Literature toolbar.
2. Enter the DOI (e.g., `10.1038/nature12345`).
3. Metadata is fetched automatically from CrossRef/DOI.org.
4. Click **Save**.

### Searching Literature

Use the search field above the list. Search format:

| Example | Description |
|--------|-----------|
| `darwin evolution` | Search in all fields |
| `title:principia` | Search only in titles |
| `tags:physics` | Filter by tags |
| `year:2023` | Filter by year |

### Actions on Literature Entries

| Action | How |
|------|------|
| Open PDF | Click the document icon on the entry |
| Create new note | **Create Note** button — creates a `.md` file with a complete template |
| Edit metadata | Click an entry → detail panel on the right |
| Add tags | In the detail panel, click **+ Tag** |
| Copy BibTeX | Right-click an entry → **Copy BibTeX** |

### Creating a Note from Literature

Click **Create Note** on a literature entry → a `papis-key.md` file is automatically created in `notes/` with a template:

```markdown
# Paper Title

Source: @papis-key

## Summary

## Important Notes

## Quotes
```

---

## 9. Backlink Graph

The right panel contains two tabs for viewing relationships between notes.

### Backlinks Tab

Displays a list of notes that have a `[[link]]` to the currently active note. Click one to open that note.

The **Rebuild** button rescans the entire vault to update backlink data.

### Graph Tab (Visualization)

An interactive graph that displays all notes as nodes and wiki-links as edges.

| Node Color | Description |
|-----------|-----------|
| Blue | Normal note |
| Orange/Red | Currently opened note |
| Gray | Orphan note (no other notes link here) |

**Interaction:**

| Action | Result |
|------|-------|
| Click node | Opens that note |
| Scroll | Zoom in/out |
| Drag background | Pan (move view) |
| Drag node | Move node position |
| Hover node | Displays note name |

**Control Buttons:**

- **Rebuild** — rescan all wiki-links.
- **Reset View** — return zoom and position to default.
- **Zoom +/−** — manual zoom.

> **Tools › Rebuild Backlink Graph** to update from the entire vault.

---

## 10. Git Synchronization

Noteration can synchronize the vault to a Git repository (e.g., GitHub).

### Requirements

- Git is installed on your system.
- The vault is already initialized as a Git repository, or you create a new repository from within Noteration.

### First-Time Setup

1. Open the **Synchronization** tab (View › Synchronization or toolbar).
2. If the vault is not yet a Git repo: click **Initialize Git**.
3. Click **Set Remote** and enter the GitHub repository URL:
   ```
   https://github.com/username/vault-name.git
   ```
4. Click **Save Remote**.
5. Click **Sync Now** for the first push.

### Synchronization

- **Ctrl+Shift+S** or toolbar **Sync** or **Tools › Synchronize Now**.
- Process logs appear in the Synchronization tab in real-time.
- Use the **Refresh Status** button to check for remote updates without performing a full sync.

### Git Status Indicators

| Badge | Description |
|-------|-----------|
| `Git: synced` (green) | Vault is synchronized with remote |
| `Git: modified` (orange) | There are local changes not yet committed |
| `Git: ↑2 ↓1` (blue) | 2 local commits not yet pushed, 1 remote commit not yet pulled |
| `Git: local only` (gray) | No remote configured |
| `Git: offline` (gray) | Folder is not a Git repository |

### Conflict Resolution

If a conflict occurs during synchronization, the **Conflict Resolution** dialog appears automatically:

1. Each conflicting file is displayed in its own tab.
2. The **left** panel shows the local version ("mine").
3. The **right** panel shows the remote version ("theirs").
4. The **bottom** panel is the resolution editor — can be edited freely.
5. Use the buttons:
   - **Take all mine** — use the local version.
   - **Take all theirs** — use the remote version.
   - **Merge both** — combine both as a starting point.
6. Click **Apply Resolution** to finish and continue the push.

### Commit History

The Synchronization tab displays the last 20 commits with columns:
SHA, message, author, and time.

---

## 11. Settings

Open via **Tools › Settings** or `Ctrl+,`.

### Editor Tab

| Setting | Description |
|-----------|-----------|
| **Font** | Editor font family (default: Consolas) |
| **Font Size** | Font size in pt (default: 12) |
| **Tab Width** | Number of spaces per Tab (default: 2) |
| **Line Numbers** | Show/hide line numbers |
| **Auto Indent** | Follow previous line's indentation on Enter |
| **Auto Save** | Enable/disable autosave |
| **Autosave Interval** | Delay between autosaves in seconds |

### PDF Tab

| Setting | Description |
|-----------|-----------|
| **Renderer** | `qtpdf` (built-in) or `pymupdf` (requires `pip install pymupdf`) |
| **Default Highlight Color** | Highlight color for PDF text selection |

### Papis Tab

| Setting | Description |
|-----------|-----------|
| **Library Path** | Folder where Papis stores literature entries |

### Synchronization Tab

| Setting | Description |
|-----------|-----------|
| **Remote** | Git remote name (default: `origin`) |
| **Branch** | Synchronized branch (default: `main`) |
| **Strategy** | `rebase` (default), `merge`, or `stash` |

### Appearance Tab

| Setting | Description |
|-----------|-----------|
| **Theme** | `light`, `dark`, or `system` (follows OS theme) |

Theme changes are applied **immediately** (live preview) when selected.
Click **Cancel** to revert to the previous theme.

---

## 12. Full Shortcuts

### File & Notes

| Shortcut | Action |
|----------|------|
| `Ctrl+N` | New note |
| `Ctrl+S` | Save note |
| `Ctrl+Shift+S` | Synchronize Git now |
| `Ctrl+W` | Close active tab |
| `Ctrl+Q` | Exit application |

### Editor

| Shortcut | Action |
|----------|------|
| `Ctrl+F` | Global Vault Search (applies to the entire vault) |
| `Ctrl+Shift+V` | Toggle Edit ↔ View mode (preview) |
| `Ctrl+Click` | Wiki-link navigation |
| `Tab` | Indent |
| `Shift+Tab` | Unindent |

### Navigation

| Shortcut | Action |
|----------|------|
| `F1` | Open this user guide |
| `F2` | Open Research and Writing briefing |
| `F11` | Toggle Focus Mode |
| `Esc` | Exit Focus Mode (from Normal mode) |
| `Ctrl+,` | Open Settings |

### Dialogs

| Shortcut | Action |
|----------|------|
| `Enter` | Confirm |
| `Esc` | Close dialog |

---

## 13. Focus Mode & Vim Keybindings

Focus Mode is designed for distraction-free writing. It can be toggled via **View › Focus Mode** or by pressing **F11**.

### Features

- **Minimalist Interface**: Fullscreen view where the menu bar, status bar, and toolbars are hidden.
- **Centered Layout**: The editor stays in the center of the screen with a width of 50% of the window.
- **Vim Integration**: A powerful modal editing system inspired by Vim.

### Vim Modes

| Mode | Trigger | Description |
|------|---------|-------------|
| **NORMAL** | `Esc` | Default navigation mode. Move with `h`, `j`, `k`, `l`, `w`, `b`, `0`, `$`, `G`, `g`. |
| **INSERT** | `i`, `a`, `o` | Standard typing mode. |
| **VISUAL** | `v`, `V` | Selection mode for characters (`v`) or full lines (`V`). |
| **COMMAND** | `:` | Input commands like `:w` (save) or `:q` (exit focus mode). |

### Common Vim Commands

| Key | Action |
|-----|--------|
| `u` | Undo |
| `x` | Delete character |
| `p` | Paste |
| `y` | Yank (Copy) in Visual mode |
| `d` | Delete/Cut in Visual mode |

---

## 14. `config.toml` Configuration

The configuration file is located at `<vault>/.noteration/config.toml`.
It is edited automatically via the Settings dialog, or can be edited manually with a text editor.

```toml
[general]
autosave          = true
autosave_interval = 30           # seconds (5–600)

[editor]
tab_width         = 2            # spaces per Tab (1–8)
font_family       = "Consolas"   # monospace font name
font_size         = 12           # font size in pt (8–32)
show_line_numbers = true
auto_indent       = true

[pdf]
renderer               = "qtpdf"     # "qtpdf" or "pymupdf"
default_highlight_color = "#FFEB3B"  # hex color

[papis]
library_path = "~/noteration/literature"   # absolute path or ~

[sync]
remote        = "origin"
branch        = ""        # empty = auto-detect active branch
strategy      = "rebase"  # "rebase", "merge", or "stash"

[ui]
theme           = "system"   # "light", "dark", or "system"
sidebar_visible = true
```

---

## 14. Vault Structure

```
~/vault-name/
├── .noteration/
│   ├── config.toml          # Configuration for this vault
│   ├── db.sqlite            # PDF index cache
│   └── link_graph.json      # Backlink graph cache (auto-generated)
│
├── notes/                   # All Markdown notes
│   ├── index.md             # Main note (convention)
│   ├── topic-a.md
│   └── subfolder/
│       └── topic-b.md
│
├── literature/              # Managed by Papis
│   ├── darwin1859/
│   │   ├── info.yaml        # Entry metadata
│   │   └── darwin1859.pdf   # PDF file (optional)
│   └── einstein1905/
│       └── info.yaml
│
├── annotations/             # PDF Annotations (JSON, non-destructive)
│   ├── <sha256-hash>.json
│   └── images/
│
└── attachments/             # Images and note attachments
    ├── 20240101_diagram.png
    └── data-table.csv
```

### Files Synchronized via Git

| Synchronized | Not Synchronized |
|---------------|---------------------|
| `notes/**/*.md` | `literature/**/*.pdf` (large) |
| `annotations/*.json` | `.noteration/db.sqlite` (cache) |
| `attachments/*` | `__pycache__/` |
| `literature/**/*.yaml` | `.DS_Store`, `Thumbs.db` |
| `.noteration/config.toml` |`.noteration/*.log` |

---

## 15. Frequently Asked Questions (FAQ)

**Q: Do I have to use Papis?**
A: No. Noteration can be used as a Markdown editor + Git sync without Papis. Citation features, `@` autocomplete, and the Literature tab will not be available, but the editor, wiki-links, backlink graph, and synchronization will still work fully.

**Q: Is there a fee to use Noteration?**
A: No. Noteration is open-source software under the MIT license, free forever.

**Q: Can I use an existing vault from Obsidian?**
A: You can point Noteration to an existing Obsidian vault folder. The application will open and read .md files. However, Noteration assumes all notes are in the `notes/` subfolder, while Obsidian usually puts notes directly in the vault root. This might cause some features to not work optimally.

The easiest way: move all Obsidian .md files to the `notes/` subfolder within the same vault. Obsidian can be configured to set "Default location for new notes" to the `notes/` folder so both applications can coexist in the same vault without conflict.

**Q: My annotations disappeared after moving a PDF file.**
A: Annotations are stored based on the SHA-256 hash of the PDF content, not by file path. If the PDF content doesn't change, annotations can still be found even if the path changes.

**Q: How do I backup my vault?**
A: The easiest way is with Git — pushing to GitHub makes GitHub your automatic backup. Alternatively, copy the entire vault folder to another location. Make sure to include the `.noteration/` subfolder as it stores `config.toml` and `link_graph.json`.

**Q: Can I open Noteration on multiple devices?**
A: Yes, with Git sync. Push from device A, pull from device B. If two devices edit the same file simultaneously, the Conflict Resolution dialog will help merge the changes.

**Q: Can it handle sync for private Git repos?**
A: Yes, so your vault notes are only accessible and synchronized on your own devices. Not open to the public.

---

*This guide applies to Noteration v1.1.2*

