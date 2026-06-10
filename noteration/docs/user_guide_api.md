# Noteration REST API User Guide (`ntr-api`)

The Noteration REST API provides a lightweight HTTP interface to your research vault. It allows external tools and scripts to query your notes and literature database.

## Installation

The API requires extra dependencies. To install them, run:

```bash
pip install -e ".[api]"
```

## Running the Server

### Start via CLI
Start the API server using the `ntr api start` command:

```bash
ntr api start --vault ~/my-vault --port 8765
```

### GUI Configuration & Control
In the Noteration GUI, go to **Settings > API**. 
- Toggle **"Enable API Server on startup"** to automate launching.
- Configure **Host** and **Port**.
- Generate and manage your **API Key**.

---

## Security (API Key)

All requests (except basic health checks) require an `X-API-Key` header if a key is configured in your settings.

```bash
curl -H "X-API-Key: YOUR_KEY" http://127.0.0.1:8765/notes
```

---

## API Endpoints

### Notes Management
- `GET /notes`: List all notes with basic metadata.
- `GET /notes/{id}`: Get full Markdown content and backlinks.
- `POST /notes`: Create a new note. Body: `{"note_id": "name", "content": "# Content"}`.
- `PUT /notes/{id}`: Update an existing note. Body: `{"content": "New content"}`.
- `DELETE /notes/{id}`: Permanently delete a note.

### Searching
- `GET /search?q=<query>&limit=10`: Perform full-text search across all notes.

### Vault System
- `GET /graph/stats`: Retrieve vault statistics (node count, links, hub).
- `GET /sync/status`: Check the current Git synchronization status.

---

## Integration Examples

### Fetch notes using `curl`
```bash
curl http://127.0.0.1:8765/notes
```

### Integration from a Python script
```python
import requests

HEADERS = {"X-API-Key": "your-secret-key"}
BASE_URL = "http://127.0.0.1:8765"

# Search for a note
response = requests.get(f"{BASE_URL}/search", params={"q": "darwin"}, headers=HEADERS)
results = response.json()

for r in results:
    print(f"[{r['id']}] {r['snippet']}")
```

---

## Security & Network Note

By default, the server binds to `127.0.0.1`, meaning it is **only accessible from your local machine**. If you bind to `0.0.0.0` to access it over a network, ensure your firewall is configured correctly and that you have set a strong API Key.
