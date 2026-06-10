# Noteration User Guide

**Version 2.0.0**

Noteration is a desktop application for integrated research note management. This application combines a Markdown editor, a PDF viewer with non-destructive annotations, literature management via Papis, and Git synchronization — all in one interface.

---

## Table of Contents

1. [Getting Started — Vault](#1-getting-started--vault)
2. [Main Interface](#2-main-interface)
3. [Markdown Editor](#3-markdown-editor)
4. [Wiki-links Between Notes](#4-wiki-links-between-notes)
5. [Citations and @citation Autocomplete](#5-citations-and-citation-autocomplete)
6. [Global Vault Search (FTS5)](#6-global-vault-search-fts5)
7. [Tag System #tag](#7-tag-system-tag)
8. [PDF Viewer and Annotations](#8-pdf-viewer-and-annotations)
9. [Literature Management (Papis)](#9-literature-management-papis)
10. [Backlink Graph](#10-backlink-graph)
11. [Git Synchronization](#11-git-synchronization)
12. [Settings](#12-settings)
13. [Complete Keyboard Shortcuts](#13-complete-keyboard-shortcuts)
14. [Focus Mode and Vim Keybindings](#14-focus-mode-and-vim-keybindings)
15. [Split View](#15-split-view)
16. [Document Export](#16-document-export)
17. [Vault Encryption](#17-vault-encryption)
18. [Navigation History](#18-navigation-history)
19. [`config.toml` Configuration](#19-configtoml-configuration)
20. [Vault Structure](#20-vault-structure)
21. [Frequently Asked Questions (FAQ)](#21-frequently-asked-questions-faq)

---

## 1. Getting Started — Vault

Noteration works based on the **Vault** concept: a folder that serves as the main project directory. The Vault is the center for all notes, literature, annotations, and attachments.

Unlike cloud-based applications, Noteration stores all data locally — users have full control over their own data.

### Creating a New Vault

1. Launch Noteration — the **Select Vault** dialog appears automatically.
2. Click **Create New Vault**.
3. Enter the vault name (e.g., "Thesis Research" or "Second Brain").
4. Choose the folder location on the hard drive.
5. Click **Create** — the folder along with its subdirectory structure will be created automatically:

```
new-vault/
├── notes/          ← Markdown notes
├── literature/     ← Papis library
├── annotations/    ← PDF highlight data
├── attachments/    ← images and attachments
└── .noteration/    ← internal settings and cache
```

### Opening an Existing Vault

1. In the **Select Vault** dialog, select a vault from the history list, or
2. Click **Open Folder…** to manually select the vault folder.

> **Tip:** Multiple vaults can be opened simultaneously — each vault opens its own `MainWindow` via **File › Open Vault…**.

### Removing a Vault from the List

Right-click on the vault in the Select Vault dialog → **Remove from List**.
This only removes the entry from history, **does not** delete the folder or its contents from disk.

---

## 2. Main Interface

```
┌──────────────────────────────────────────────────────────────────────┐
│  Toolbar: + Note │ Save │ Literature │ Sync │ Git: synced ●          │
├───────────┬───────────────────────────────────────────┬──────────────┤
│           │                                           │              │
│ Navigator │              Main Tab                     │  Backlinks   │
│           │   (Editor / PDF / Literature / Sync)      │  ──────────  │
│ ▸ Notes   │                                           │  Graph       │
│   index   │                                           │              │
│   research│                                           │              │
│ ──────── │                                           │              │
│ ▸ Tags    │                                           │              │
│   #method │                                           │              │
│ ──────── │                                           │              │
│ ▸ Outline │                                           │              │
│   # Chapter 1 │                                       │              │
│ ──────── │                                           │              │
│ ▸ Citations│                                          │              │
│   @darwin │                                           │              │
│           │                                           │              │
├───────────┴───────────────────────────────────────────┴──────────────┤
│ note.md │ Ln 12, Col 5 │ 342 words │ ● synced │ my-vault        │
└──────────────────────────────────────────────────────────────────────┘
```

### Left Panel — Navigator

The Navigator has several collapsible sections:

| Section | Content |
|--------|-----|
| **Notes** | Markdown file/folder tree. Supports drag-and-drop. |
| **Tags** | List of all `#tag` from notes (🏷️) and literature tags (📚). |
| **Related PDFs** | PDFs from the Papis library cited in the active note. Click to open. |
| **Outline** | List of headings (`#`, `##`, `###`) from the active note. Click to jump. |
| **Citations** | List of `@citation-key` used in the active note. Click to jump. |

### Menu Bar

| Menu | Content |
|------|-----|
| **File** | New Note, Open Vault, Save, Export (HTML/PDF/DOCX/LaTeX/ODT/TXT), Exit |
| **View** | Toggle sidebar/right panel, Focus Mode, Literature, Synchronization |
| **Search** | Global vault search |
| **Tools** | Sync, Export BibTeX, Build Backlink Graph, Scan PDF Index, Encrypt Vault, Settings |
| **Help** | Check for Update, Guide, Research and Writing, About |

### Right Panel — Link Graph

Contains two tabs:

- **Backlinks** — list of other notes that link to the currently open note.
- **Graph** — visualization of the wiki-link network across the entire vault.

### Status Bar

| Indicator | Description |
|-----------|-----------|
| File name | The active note. Symbol `*` means there are unsaved changes. |
| `Ln X, Col Y` | Cursor position (line and column). |
| `N words` | Number of words in the active note (excluding front-matter and code). |
| `● synced` / `● modified` / `○ offline` / `↑N ↓N` | Git repository status (synced, modified, offline, or ahead/behind commit counts). |
| Vault Name | The currently open vault. |

---

## 3. Markdown Editor

### Creating a New Note

- **Ctrl+N** or toolbar **+ Note** → name and folder dialog appears.
- Enter the file name (without `.md`) and choose a subfolder if needed.
- Click **Create** — the file opens directly in the editor.

### Saving

- **Ctrl+S** for manual save.
- Autosave runs automatically every 30 seconds (configurable in Settings).
- When closing an unsaved tab, the file is saved automatically.

### Edit Mode vs View Mode (Preview)

Each editor tab has two modes:

| Mode | Display | How to Switch |
|------|----------|--------------|
| **Edit** | Raw Markdown text with syntax highlighting | `Edit` button in tab toolbar |
| **View** | HTML rendered from Markdown | `View` button in tab toolbar, or `Ctrl+Shift+V` |

- Right-click in Edit mode: undo, redo, copy, cut, paste, select all, find and replace.
- Right-click in View mode: export to HTML, TXT, PDF, DOCX, LaTeX, ODT.

### Supported Markdown Syntax

````markdown
# Heading 1
## Heading 2
### Heading 3

**bold**   _italic_   ~~strikethrough~~   `inline code`   ==highlight==

- [ ] checklist item
- regular item
1. numbered list

> blockquote

```python
def hello():
    print("Noteration!")
```

![Image](attachments/image.png)
[External Link](https://example.com)
````

### Additional Syntax

Noteration supports advanced Markdown extensions:

| Feature | Syntax | Example |
|-------|---------|--------|
| Highlight | `==text==` | ==important text== |
| Strikethrough | `~~text~~` | ~~no longer valid~~ |
| Superscript | `text^sup^` | E=mc^2^ |
| Checklist | `- [ ] item` | Interactive checkbox |

### Math (LaTeX)

Noteration supports rendering mathematical formulas using MathJax:

```markdown
Inline formula: $E = mc^2$

Display formula:
$$
\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}
$$
```

Formulas are rendered visually in View Mode. Double-backslash (`\\`) for new lines in equations is handled correctly.

### Pasting and Inserting Images

- **Drag & drop** image files from file manager to editor → image is automatically copied to `attachments/` and `![]()` syntax is inserted.
- **Paste** image from clipboard (Ctrl+V after screenshot) → same as drag & drop.

### Line Numbers and Active Line Highlight

Line numbers are displayed on the left side of the editor. The active line is highlighted with a different color. Both can be disabled in **Settings › Editor**.

---

## 4. Wiki-links Between Notes

Wiki-links are a way to connect notes to each other, similar to Obsidian or Roam.

### Syntax

```markdown
See [[note-name]] for more details.
Or with alias: [[note-name|display text]]
```

### Navigation

- **Ctrl+Click** on `[[note-name]]` in the editor → opens that note.
- If the note does not exist, a dialog appears offering to **create a new note**.
- Click backlink in the right panel → opens the source note.

### Link Resolution

Noteration recursively searches for the file `note-name.md` inside the `notes/` folder. Names are case-insensitive and do not require the `.md` extension.

### Drag-and-Drop in Navigator

Note files and folders can be moved using drag-and-drop in the Navigator panel:

- Drag file to target folder to move it.
- Drag to empty area to move to root `notes/`.
- If name already exists in destination, confirmation dialog appears.
- Open tabs are automatically updated to follow the new path.

---

## 5. Citations and @citation Autocomplete

### How to Insert Citations

In the editor, type `@` followed by a few letters from the title, author, or citation key:

```markdown
As explained by @darwin1859 in his theory of evolution...
```

Suggestion list appears automatically — select with arrow keys and `Enter`.

### Supported Citation Formats

The editor's citation feature supports the basic `@key` format (e.g., `@darwin1859`). 

When in **View Mode**, the rendering engine automatically formats these citation keys according to the selected CSL style.

| Format | Example |
|--------|--------|
| Citation key | `@darwin1859` |

> **Note:** Currently, Noteration only supports basic citation keys (`@key`). Advanced citation formats like page numbers (e.g., `[p. 42]`) or multiple citations in a single block (e.g., `@key1; @key2`) are not supported.

### Jumping to Citations

In the **Citations** section of the Navigator panel, click `@key` to jump directly to its occurrence in the note.

### CSL Citation Styles

Noteration supports rendering citations according to CSL (Citation Style Language) standards using `citeproc-py`.

To change citation style:
1. Open **Settings › Papis**.
2. In the **Citation Style** dropdown, select the desired style (APA, IEEE, MLA, Chicago, Vancouver).
3. Click **OK** — changes apply to all rendering in View Mode.

Custom styles: place `.csl` file in the `.noteration/` folder and select from Settings dropdown.

### BibTeX Export

- **Tools › Export BibTeX (all)** — export entire library to one `.bib` file.
- **Tools › Export BibTeX (this note)** — export only citations used in the active note.

---

## 6. Global Vault Search (FTS5)

Open via **Search** menu or **Ctrl+F** (applies to the entire vault, regardless of active tab).

Noteration uses the **SQLite FTS5** engine — search is much faster than previous versions, especially for vaults with hundreds of notes.

### Search Scope

| Icon | Source | What is Searched |
|------|--------|-------------|
| 📄 | **Notes** | Content of all `.md` files in `notes/` folder |
| 📚 | **Literature** | Titles, authors, abstracts, and tags from Papis library |
| 📌 | **Annotations** | Highlight text and notes made in PDFs |

### How to Use

1. Type keywords — results appear automatically after a short pause.
2. Use **Case Sensitive** and **Regex** filters for more specific searches.
3. **Scope** filter to limit search: All / Notes / Literature / Annotations.
4. Click result to open: note opens in editor tab, literature opens in Literature tab, annotation opens PDF on relevant page.

### Tag Search

Type `#tag-name` in the search field to find all documents with that tag across notes and literature.

### Pre-fill from Selection

If text is selected in the editor when the search dialog is opened, that text automatically becomes the initial keyword.

### Incremental Index

FTS5 updates its index incrementally every time a note is saved — no manual rebuild needed unless there are major vault changes.

---

## 7. Tag System #tag

Noteration introduces a first-class tag system extracted directly from Markdown content.

### How to Add Tags

Simply write `#tag` anywhere in the note text:

```markdown
# Research Methodology

This research uses a #qualitative and #ethnographic approach
to analyze the #education phenomenon in remote areas.
```

Tags are extracted automatically when the note is saved — no additional steps needed.

### Tags Panel in Sidebar

The **Tags** panel in Navigator displays all tags in the vault:

- 🏷️ **Note tags** — extracted from `.md` files
- 📚 **Literature tags** — from `tags` field in Papis `info.yaml`

Click a tag in the panel → global search is immediately run for that tag, showing all notes and literature with the same tag.

### Tag Format Rules

- Use letters, numbers, and hyphens: `#machine-learning`, `#chapter-3`
- Tags must be preceded by a space or at the start of a line (not inside inline code)
- Case-insensitive during search: `#Qualitative` and `#qualitative` are considered the same

---

## 8. PDF Viewer and Annotations

### Opening PDFs

- From **Literature** tab: click PDF icon on literature entry.
- From **Related PDFs** panel in sidebar.
- Drag & drop PDF file to Noteration window.

### PDF Navigation

| Action | Method |
|------|------|
| Change page | Arrow buttons in viewer toolbar, or scroll |
| Zoom | `+` / `-` buttons in toolbar, or `Ctrl+Scroll` |
| Jump to page | Type page number in navigation field |
| Text search | `Ctrl+F` inside PDF tab |

### Toggle Annotation Panel

Press **Ctrl+Alt+A** or click button in toolbar to show/hide annotation panel on the right, providing a wider reading view.

### Highlight and Annotations

1. Select text on the PDF page with mouse.
2. Click **🟡 Highlight** button in toolbar to activate highlight mode, then drag over the text.
3. Right annotation panel offers options:
   - **Highlight** — highlight text with color (default yellow, configurable in Settings).
   - **Note (💬)** — add text note at specific position.
   - **Insert to Editor** — insert text as blockquote to active note editor, complete with automatic `@citation-key`.
4. Use **🖼 Image** to capture image area from PDF. Images saved to `annotations/images/`.
5. **🔖** to add bookmark on current page.

### Annotation Storage (Non-Destructive)

Annotations **do not modify the original PDF file**. All annotations are saved in JSON format in the `annotations/` folder, named based on SHA-256 hash of PDF content:

```
annotations/
├── a3f8c2...d1b9.json   ← annotation for one PDF
└── images/
    └── darwin1859_ann-abc123.png
```

These JSON files are synchronized via Git, so annotations can be shared or synced across devices.

---

## 9. Literature Management (Papis)

The Literature tab displays the contents of your [Papis](https://papis.io/) library.

### Adding New Entries

#### Via DOI

1. Click **+ Add** in Literature toolbar.
2. Enter DOI (e.g. `10.1038/nature12345`).
3. Metadata is fetched automatically from CrossRef/DOI.org.
4. Click **OK**.

#### Via arXiv

1. In Add dialog, enter arXiv URL (e.g. `https://arxiv.org/abs/2404.14339`).
2. Metadata and preprint information fetched automatically.

#### Via ISBN

1. Enter ISBN number for book (e.g. `9780131103627`).
2. Metadata fetched from OpenLibrary.

#### Manual

Fill title, author, year, journal, and other fields manually, then select PDF if available.

### Searching Literature

Use the search field above the list. Search format:

| Example | Description |
|--------|-----------|
| `darwin evolution` | Search all fields |
| `title:principia` | Search only in title |
| `tags:physics` | Filter by tag |
| `year:2023` | Filter by year |

### Collection Filter

Use dropdown to the left of search field to filter by collection. Collections managed via `collections` field in `info.yaml`.

### Actions on Literature Entries

| Action | Method |
|------|------|
| Open PDF | Click document icon on entry |
| Copy @key | Right-click entry → **Copy @key** |
| Create new note | **Create Note** button — creates `.md` file with complete template |
| Edit title | Click entry → detail panel on right |
| Edit author | Click entry → detail panel on right |
| Add tag | In detail panel, click **+ Tag** |
| Add collection | In detail panel, click **+ Collection** |
| Attach file | **Attach File** button in detail panel |
| Delete Document | Click entry → detail panel on right |

### Creating Note from Literature

Click **Create Note** on literature entry → `papis-key.md` file is automatically created in `notes/` with template:

```markdown
# Paper Title

Source: @papis-key

## Summary

## Important Notes

## Quotes
```

---

## 10. Backlink Graph

The right panel contains two tabs for viewing relationships between notes.

### Backlinks Tab

Displays list of notes that have `[[link]]` to the currently active note. Click one to open the source note.

**Rebuild** button rescans the entire vault to update backlink data.

### Graph Tab (Visualization)

Interactive graph showing all notes as nodes and wiki-links as edges.

| Node Color | Description |
|-----------|-----------|
| Blue | Normal note |
| Orange/Red | Currently open note |
| Gray | Orphan note (no other notes link to it) |

**Interactions:**

| Action | Result |
|------|-------|
| Click node | Opens that note |
| Scroll | Zoom in/out |
| Drag background | Pan (move view) |
| Hover node | Shows note name |

**Control Buttons:**

- **⊡ Fit** — reset zoom and position to default.
- **◎** — toggle orphan notes display.

> **Tools › Rebuild Backlink Graph** to update from entire vault.

---

## 11. Git Synchronization

Noteration can synchronize your vault to a Git repository (e.g., GitHub) for backup and multi-device access.

### Requirements
*   Git installed on the system.
*   Vault already initialized as a Git repository, or create a new repository from within Noteration.

### First Time Setup

1. Use **Shortcut:** `Ctrl+Shift+S`, **Sync** toolbar button, or **Tools › Sync Now**.
2. If the vault is not yet a Git repository: click **Initialize Git**.
3. Click **Configure Remote**.
4. Enter the Remote Name (default: `origin`) and **Repository URL** (e.g., `https://github.com/username/vault-name.git`). Click **OK**.
5. Click **Sync Now**.

> **Important Note for New Repositories:**
> If your remote repository on GitHub is completely empty (no `README.md` or existing branches), the initial **Sync Now** click will fail during the pull phase.
> *   **Recommended:** Initialize your GitHub repository with a `README.md` file when creating it.
> *   **If already empty:** Perform an initial push via the terminal inside your vault folder before using Noteration's sync:
```bash
   git push -u origin main
   # (Use 'master' instead of 'main' if your local branch is named master)
```
> After this manual push, the **Sync Now** button will function automatically for subsequent synchronizations.

### Branch Auto-detect

Noteration automatically detects the active branch — no need to configure the branch name manually unless required for special workflows. Leave the branch field empty in **Settings** to enable auto-detection.

### Git Status Indicators

| Badge | Description |
|-------|-----------|
| `Git: synced` (green) | Vault synchronized with remote |
| `Git: modified` (orange) | Local changes not yet committed |
| `Git: ↑2 ↓1` (blue) | 2 local commits not pushed, 1 remote commit not pulled |
| `Git: local only` (gray) | No remote configured |
| `Git: offline` (gray) | Folder is not a Git repository |

### Conflict Resolution

If conflicts occur during synchronization, **Conflict Resolution** dialog appears automatically:

1. Each conflicting file is shown in its own tab.
2. **Left** panel shows local version ("mine").
3. **Right** panel shows remote version ("theirs").
4. **Bottom** panel is resolution editor — can be freely edited.
5. Use buttons:
   - **Take all mine** — use local version.
   - **Take all theirs** — use remote version.
   - **Merge both** — combine both as starting point.
6. Click **Apply Resolution** to finish and continue push.

### Commit History

Synchronization tab displays the last 25 commits with columns: SHA, message, author, and time.

---

## 12. Settings

Open via **Tools › Settings** or `Ctrl+,`.

### Editor Tab

| Setting | Description |
|-----------|-----------|
| **Font** | Editor font family name (default: Consolas) |
| **Font Size** | Font size in pt (default: 12) |
| **Tab Width** | Spaces per Tab (default: 2) |
| **Line Numbers** | Show/hide line numbers |
| **Auto Indent** | Follow previous line indentation on Enter |
| **Auto Save** | Enable/disable autosave |
| **Autosave Interval** | Interval between autosaves in seconds |

### PDF Tab

| Setting | Description |
|-----------|-----------|
| **Renderer** | `qtpdf` (default) or `pymupdf` (requires `pip install pymupdf`) |
| **Default Highlight Color** | Highlight color for PDF text selection |

### Papis Tab

| Setting | Description |
|-----------|-----------|
| **Library Path** | Folder where Papis stores literature entries |
| **Citation Style** | CSL citation style: APA, IEEE, MLA, Chicago, Vancouver |

### Synchronization Tab

| Setting | Description |
|-----------|-----------|
| **Remote** | Git remote name (default: `origin`) |
| **Branch** | Branch to synchronize (empty = auto-detect) |
| **Strategy** | `rebase` (default), `merge`, or `stash` |

### Security Tab

| Setting | Description |
|-----------|-----------|
| **Status** | Displays whether the vault is currently encrypted or plaintext. |
| **Permanently Decrypt** | Button to initiate permanent decryption of the vault. |

### Appearance Tab

| Setting | Description |
|-----------|-----------|
| **Theme** | `light`, `dark`, or `system` (follows OS theme) |

Theme changes are applied **live** when selected. Click **Cancel** to revert to previous theme.

---

## 13. Complete Keyboard Shortcuts

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
| `Ctrl+F` | Global Vault Search |
| `Ctrl+Shift+V` | Toggle Edit ↔ View mode (preview) |
| `Ctrl+Click` | Wiki-link navigation |
| `Tab` | Indent |
| `Shift+Tab` | Unindent |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |

### Navigation

| Shortcut | Action |
|----------|------|
| `Alt+←` | Back to previous note (history) |
| `Alt+→` | Forward to next note (history) |
| `F1` | Open this user guide |
| `F2` | Open Research and Writing guide |
| `F11` | Toggle Focus Mode |
| `Esc` | Exit Focus Mode (from Normal mode) |
| `Ctrl+,` | Open Settings |

### PDF Viewer

| Shortcut | Action |
|----------|------|
| `Ctrl+F` | Search text in PDF |
| `Ctrl++` / `Ctrl+=` | Zoom in |
| `Ctrl+-` | Zoom out |
| `PgDown` | Next page |
| `PgUp` | Previous page |
| `Ctrl+Alt+A` | Toggle annotation panel |

### Dialogs

| Shortcut | Action |
|----------|------|
| `Enter` | Confirm |
| `Esc` | Close dialog |

---

## 14. Focus Mode and Vim Keybindings

Focus Mode is designed for distraction-free writing. Toggle via **View › Focus Mode** or press **F11**.

### Focus Mode Features

- **Minimalist Interface**: Fullscreen view with menu bar, status bar, toolbar, and hidden sidebar.
- **Centered Layout**: Editor in the center of the screen with 50% window width.
- **Vim Integration**: Modal editing system inspired by Vim.

### Vim Modes

| Mode | Trigger | Description |
|------|---------|------------|
| **NORMAL** | `Esc` | Default navigation mode |
| **INSERT** | `i`, `a`, `o` | Regular typing mode |
| **VISUAL** | `v` | Character selection mode |
| **LINE VISUAL** | `V` | Full line selection mode |
| **COMMAND** | `:` | Command mode |

### Navigation in NORMAL Mode

| Key | Action |
|--------|------|
| `h` / `l` | Left / Right |
| `j` / `k` | Down / Up |
| `w` | Jump to start of next word |
| `b` | Jump to start of previous word |
| `0` | Start of line |
| `$` | End of line |
| `G` | Last line of document |
| `g` (twice) | First line of document |

### Common Vim Commands

| Key | Action |
|--------|------|
| `i` | Enter INSERT before cursor |
| `a` | Enter INSERT after cursor |
| `o` | New line below, enter INSERT |
| `u` | Undo |
| `x` | Delete character at cursor |
| `p` | Paste |
| `y` | Yank (copy) in Visual mode |
| `d` | Delete/cut in Visual mode |

### COMMAND Mode Commands

| Command | Action |
|----------|------|
| `:w` | Save note |
| `:q` | Exit Focus Mode |

### Exiting Focus Mode

Press **F11** or **Esc** (from NORMAL mode) to return to normal interface.

---

## 15. Split View

Noteration supports vertical split view, allowing side-by-side editing and reading.

### How to Use Split View

1. Right-click on tab in main tab bar.
2. Select **Open Split View** (if split not active) or **Move to Split View** (if split active).
3. Tab is moved to right panel.

To move tab back to main panel: right-click on tab in split panel → **Move to Main View**.

### Automatic Closing

When the last tab in the split panel is closed, the split panel is automatically hidden — window returns to single panel view.

### Active Pane

Click anywhere in the panel to activate it. All keyboard actions (save, search, etc.) apply to the active pane. Active pane is indicated by focused tab.

### Usage Examples

- Read note in left panel while editing new note in right panel.
- Open PDF in one panel and write summary in another.
- Compare two notes simultaneously.

---

## 16. Document Export

Noteration supports exporting notes to various formats via Pandoc.

### From File Menu

**File › Export** opens submenu:

| Format | Description |
|--------|-----------|
| **HTML** | Standalone HTML file with embedded MathJax |
| **PDF** | Requires PDF engine (pdflatex, xelatex, or weasyprint) |
| **DOCX** | Microsoft Word document |
| **ODT** | OpenDocument Text (LibreOffice) |
| **LaTeX** | `.tex` file for manual compilation |
| **Plain Text (TXT)** | Plain text without formatting |

### From Context Menu in View Mode

Right-click in preview area → select export format from menu.

### Requirements

Pandoc must be installed on system for DOCX, ODT, LaTeX, and PDF export:

```bash
# Linux
sudo apt install pandoc

# macOS
brew install pandoc

# Windows
winget install JohnMacFarlane.Pandoc
```

For PDF export, install one PDF engine:
```bash
# Lightweight option
pip install weasyprint

# Full option (LaTeX)
sudo apt install texlive-xetex
```

### BibTeX Export

Available specifically for literature references:

- **Tools › Export BibTeX (all)** — entire library.
- **Tools › Export BibTeX (this note)** — only citations in active note.

---

## 17. Vault Encryption

Noteration provides at-rest encryption using the [age](https://age-encryption.org) format, with cryptographic operations natively integrated into the application for seamless security.

> ⚠️ **Warning:** Ensure private key is stored securely before encrypting vault. Losing private key means losing access to all data. Encryption can be enabled or permanently disabled at any time through the settings.

### Ideal Scenario:

1. Prepare the Vault locally.
2. Perform encryption (Tools › Encrypt Vault) locally while the vault is still clean or before it is connected to an online repository.
3. Initialize Git (git init) in the vault folder that has already been encrypted.
4. Perform the first push to GitHub.

By following this workflow, your repository will contain only encrypted data from the very beginning, your Git history will remain clean from any data leaks, and the security of your research data will be much better ensured.

### Enabling Encryption

1. Open **Tools › Encrypt Vault (age)…**.
2. Click **Generate Keypair** — new keypair created automatically.
3. **Save private key** in password manager or secure location. Private key is shown only once.
4. Confirm and click **Encrypt** — encryption process starts.
5. Progress bar shows per-file encryption progress.
6. After completion, application needs to be restarted.

### Workflow After Encryption

Every time Noteration is opened with encrypted vault:

1. **Unlock Vault** dialog appears automatically.
2. Enter private key (paste from password manager).
3. Click **Unlock** — files decrypted to temporary session directory.
4. Work normally. Original files remain encrypted on disk.
5. When application is closed, session directory is automatically cleaned.

### Encrypted Files

| Encrypted | Not Encrypted |
|-----------|-----------------|
| `notes/**` | `.noteration/config.toml` |
| `literature/**` | `.noteration/search.db` |
| `annotations/**` | `.noteration/*.log` |
| `attachments/**` | `.git/` |

### Encryption and Git Sync

`.age` files can be synchronized via Git as usual — encrypted files do not contain plaintext data. Remote repository (GitHub) only stores encrypted data.

### Encrypting a Synced Vault

If you have a vault that is already synchronized with a Git repository (e.g., on GitHub), you can still enable encryption. However, this is a significant change to your repository.

1. **Backup:** Always create a full backup of your repository before proceeding.
2. **Maintenance Mode:** Stop synchronization on all devices. Only perform the encryption on one device.
3. **Encryption:** Follow the [Enabling Encryption](#enabling-encryption) steps. The application will convert your files to encrypted format (`.age`).
4. **Git Commit:** Noteration will automatically handle the deletion of plaintext files (`git rm`) and the addition of encrypted files (`git add`). Commit these changes to your Git repository.
5. **Sync:** Push your changes to your remote repository (`git push`).
6. **Device Sync:** On all other devices, perform a `git pull`. You will need to import the same private key into the Noteration "Unlock Vault" dialog on these devices to access the data.

> ⚠️ **Note:** After this transition, the files in your remote repository (e.g., GitHub) will no longer be human-readable. You will not be able to browse or read your notes directly on the GitHub website. Always ensure your private key is backed up securely, as it is the only way to decrypt your data on any device.

### Permanently Decrypting a Vault

If you decide to revert an encrypted vault to a standard plaintext vault:

1. Open the encrypted vault in Noteration.
2. Go to **Settings › Security**.
3. Click **Permanently Decrypt Vault**.
4. Confirm the action.
5. Close Noteration.

Noteration will automatically decrypt your files and restore them as plaintext in your vault folder when you close the application. The `encryption_enabled` setting will be automatically turned off.

---

## 18. Navigation History

Noteration tracks recently visited notes, like web browser navigation.

### How to Use

| Shortcut | Action |
|----------|------|
| `Alt+←` | Back to previously opened note |
| `Alt+→` | Forward to next note (after going back) |

History stores up to 50 latest entries and is maintained during the application session.

### When History is Useful

- After following many wiki-links in a chain, press `Alt+←` repeatedly to return to starting point.
- When switching between source notes and reference notes.
- When doing non-linear research that frequently changes context.

---

## 19. `config.toml` Configuration

Configuration file is located at `<vault>/.noteration/config.toml`. Edited automatically via Settings dialog, or can be manually edited with text editor.

```toml
[version]
schema_version = 1           # Do not change manually

[general]
autosave          = true
autosave_interval = 30       # seconds (5–600)

[editor]
tab_width         = 2        # spaces per Tab (1–8)
font_family       = "Consolas"
font_size         = 12       # pt size (8–32)
show_line_numbers = true
auto_indent       = true

[pdf]
renderer               = "qtpdf"     # "qtpdf" or "pymupdf"
default_highlight_color = "#FFEB3B"  # hex color

[papis]
library_path   = "~/noteration/literature"  # absolute path or ~
citation_style = "apa"   # "apa", "ieee", "mla", "chicago", "vancouver"

[sync]
remote   = "origin"
branch   = ""        # empty = auto-detect active branch
strategy = "rebase"  # "rebase", "merge", or "stash"

[ui]
theme           = "system"  # "light", "dark", or "system"
sidebar_visible = true

[security]
encryption_enabled = false  # set automatically after encryption
```

### Automatic Configuration Migration

Noteration introduces configuration schema versioning. When opening a vault from an older version, configuration is automatically migrated to the latest schema — no manual action required.

---

## 20. Vault Structure

```
~/vault-name/
├── .noteration/
│   ├── config.toml          # Vault configuration
│   ├── search.db            # FTS5 Database (SQLite)
│   ├── pdf_index.json       # PDF index cache
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
│   └── images/              # Images captured from PDF
│
└── attachments/             # Note images and attachments
    ├── 20240101_diagram.png
    └── data-table.csv
```

### Files Synchronized via Git

| Synchronized | Not Synchronized |
|--------------|-------------------|
| `notes/**/*.md` | `literature/**/*.pdf` (large files) |
| `annotations/*.json` | `.noteration/search.db` (FTS cache) |
| `attachments/*` | `.noteration/link_graph.json` (graph cache) |
| `literature/**/*.yaml` | `.noteration/*.log` (logs) |
| `.noteration/config.toml` | `__pycache__/`, `.DS_Store`, `Thumbs.db` |

---

## 21. Frequently Asked Questions (FAQ)

**Q: Do I have to use Papis?**  
A: No. Noteration can be used as a Markdown editor + Git sync without Papis. Citation features, `@` autocomplete, and Literature tab will not be available, but editor, wiki-links, backlink graph, tag system, and synchronization still work fully.

**Q: Is there a cost to use Noteration?**  
A: No. Noteration is open-source software under the MIT license, free forever.

**Q: Can I use an existing Obsidian vault?**  
A: Yes. Point Noteration to the Obsidian vault folder. However, Noteration assumes all notes are in the `notes/` subfolder, while Obsidian usually puts notes directly in the vault root. Easiest way: move all `.md` files from Obsidian to the `notes/` subfolder in the same vault. Obsidian can be configured to set "Default location for new notes" to the `notes/` folder so both can coexist.

**Q: My annotations disappeared after moving the PDF file.**  
A: Annotations are stored based on the SHA-256 hash of the PDF content, not the file path. If PDF content hasn't changed, annotations can still be found even if path changes.

**Q: FTS5 search doesn't show the latest note.**  
A: FTS5 index is updated incrementally when notes are saved. If new note doesn't appear, try running **Tools › Rebuild Backlink Graph** to trigger full re-indexing.

**Q: How to backup the vault?**  
A: Easiest way is with Git — pushing to GitHub makes GitHub an automatic backup. Or copy the entire vault folder to another location. Make sure to include the `.noteration/` subfolder as it contains `config.toml` and FTS5 database.

**Q: Can I open Noteration on multiple devices?**  
A: Yes, with Git sync. Push from device A, pull from device B. If two devices edit the same file simultaneously, Conflict Resolution dialog will help merge changes.

**Q: How to use custom CSL style?**  
A: Place `.csl` file in the vault's `.noteration/` folder, then select from dropdown in **Settings › Papis › Citation Style**.

**Q: Is encryption safe for sensitive research data?**  
A: Encryption uses the `age` tool which implements modern cryptography (ChaCha20-Poly1305). Security depends on secure storage of the private key. Warning! — always keep data backup before encrypting vault for the first time.

**Q: Is sync supported for private Git repositories?**  
A: Yes. Noteration doesn't care if repository is public or private — Git handles authentication. Use SSH key or GitHub Personal Access Token for passwordless sync.

---

*This guide applies to Noteration v2.0.0*
