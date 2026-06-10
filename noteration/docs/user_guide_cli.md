# Noteration CLI User Guide (`ntr`)

The Noteration CLI (`ntr`) allows you to manage your research vault, search notes, manage literature, and synchronize changes directly from your terminal. It is designed for speed and ease of automation.

## Installation

The CLI is part of the `noteration` package. To ensure all CLI dependencies are installed, run:

```bash
pip install -e ".[cli]"
```

## Vault Discovery

The CLI needs to know where your research vault is located. It follows this priority:
1.  **`--vault` flag**: `ntr --vault ~/my-vault <command>`
2.  **`NOTERATION_VAULT` environment variable**: `export NOTERATION_VAULT=~/my-vault`
3.  **Auto-detect**: Walks up from the current directory looking for a `.noteration/` folder.
4.  **Global config**: Uses the last vault opened in the Noteration GUI.

## General Commands

### `ntr info`
Show information about the current vault, including path, note count, and encryption status.

### `ntr --version`
Show the current version of Noteration.

---

## Note Management (`ntr note`)

### List Notes
```bash
ntr note list [--folder drafts] [--json]
```

### Create and Show
```bash
ntr note new "my-new-idea"
ntr note show my-new-idea [--raw]
```

### Display Kerangka (Headings)
```bash
ntr note show my-new-idea --headings
```

### Delete Note
```bash
ntr note delete my-old-note [--confirm]
```

---

## Searching (`ntr search`)

Perform a high-performance full-text search across all notes.

```bash
ntr search "machine learning"
ntr search "sampling" --limit 5
ntr search "results" --json | jq .
```

---

## Literature Management (`ntr lit`)

### List and Show
```bash
ntr lit list
ntr lit show darwin1859
```

### Add Literature
Automatically fetch metadata from online sources or add local PDF files:
```bash
ntr lit add --doi "10.1038/nature12345"
ntr lit add --arxiv "2404.14339"
ntr lit add --pdf path/to/paper.pdf --title "My Research"
```

### Export to BibTeX
```bash
ntr lit export --output references.bib
ntr lit export --note research-paper --output paper.bib
```

---

## Graph and Tags (`ntr graph` & `ntr tags`)

### Graph Analysis
```bash
ntr graph stats                 # Overall vault statistics
ntr graph backlinks my-note     # List all notes linking to this one
ntr graph path note-a note-b    # Find shortest path (connection) between two notes
```

### Tag Management
```bash
ntr tags list [--source notes|literature]
```

---

## Exporting Documents (`ntr export`)

Export notes to professional formats. Requires **Pandoc** to be installed.
```bash
ntr export my-note --format pdf --output ~/Downloads/result.pdf
ntr export my-note --format docx
```
Supported formats: `pdf`, `docx`, `html`, `latex`, `odt`, `txt`.

---

## Synchronization (`ntr sync`)

### Check Status
```bash
ntr sync status
```

### Pull and Push
```bash
ntr sync pull
ntr sync push
```

### One-command Sync
```bash
ntr sync all -m "Updated methodology section"
```

---

## API Server Management (`ntr api`)

```bash
ntr api start [--host 127.0.0.1] [--port 8765]
ntr api status   # Check if local server is reachable
```

---

## Advanced Usage & Scripting

The `--json` flag makes `ntr` compatible with tools like `jq` and `fzf`.

**Example: Open a note in VS Code using fzf**
```bash
code "$(ntr note list --json | jq -r '.[].path' | fzf)"
```

**Example: Search and view snippets**
```bash
ntr search "evolution" --json | jq -r '.[] | "[\(.id)] \(.snippet)"'
```
