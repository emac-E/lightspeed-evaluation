# okp-mcp Solr Database Connection Guide

**Location:** `~/Work/okp-mcp`

---

## Quick Answer

**Solr connection happens in 4 places:**

1. **Configuration:** `src/okp_mcp/config.py` - defines Solr URL settings
2. **Connection Setup:** `src/okp_mcp/server.py` - initializes HTTP client and passes Solr URLs to tools
3. **Main Portal Search:** `src/okp_mcp/solr.py` - connects to `/solr/portal/select` (legacy search)
4. **RAG Searches:** `src/okp_mcp/rag/common.py` - connects to `/solr/portal-rag/*` (chunked search)

---

## 1. Configuration (Where URLs Are Defined)

**File:** `src/okp_mcp/config.py`

```python
class ServerConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MCP_",  # All env vars use MCP_ prefix
        cli_prog_name="okp-mcp",
    )

    # Main Solr instance (legacy portal core)
    solr_url: str = Field(
        default="http://localhost:8983",
        description="Base URL of the Solr instance",
    )

    # RAG Solr instance (portal-rag core with chunked docs)
    rag_solr_url: str | None = Field(
        default=None,
        description="Base URL of the RAG Solr instance. Falls back to solr_url if not set.",
    )

    @computed_field
    @property
    def solr_endpoint(self) -> str:
        """Solr select endpoint derived from solr_url."""
        return f"{self.solr_url}/solr/portal/select"
```

**Environment Variables:**
- `MCP_SOLR_URL` - Main Solr instance (default: `http://localhost:8983`)
- `MCP_RAG_SOLR_URL` - RAG Solr instance (optional, falls back to `MCP_SOLR_URL`)

**Command-line Args:**
```bash
okp-mcp --solr-url http://localhost:8983 --rag-solr-url http://localhost:8984
```

---

## 2. Connection Initialization (HTTP Client Setup)

**File:** `src/okp_mcp/server.py`

```python
@asynccontextmanager
async def _app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, AppContext]]:
    """Manage app lifecycle resources for tool execution."""
    cfg = _server_config if _server_config is not None else ServerConfig()

    # Derive endpoints from config
    solr_endpoint = cfg.solr_endpoint  # http://localhost:8983/solr/portal/select
    rag_solr_url = cfg.rag_solr_url or cfg.solr_url  # Falls back if not set

    # Log configuration
    logger.info("SOLR endpoint: %s", solr_endpoint)
    logger.info("RAG Solr URL: %s", rag_solr_url)

    # Create shared HTTP client (30 second timeout)
    client = httpx.AsyncClient(timeout=30.0)

    try:
        yield {
            "app": AppContext(
                http_client=client,           # Shared across all tools
                solr_endpoint=solr_endpoint,  # Legacy portal search
                rag_solr_url=rag_solr_url,    # RAG chunked search
                max_response_chars=cfg.max_response_chars,
                embedder=embedder,
            )
        }
    finally:
        await client.aclose()  # Clean up connection pool
```

**Key Points:**
- One shared `httpx.AsyncClient` for all Solr queries
- 30-second timeout for all requests
- Connection pool managed by httpx (reuses TCP connections)

---

## 3. Main Portal Search (Legacy Full-Doc Search)

**File:** `src/okp_mcp/solr.py`

**Function:** `_solr_query()` at line 78

```python
async def _solr_query(
    params: dict,
    client: httpx.AsyncClient | None = None,
    *,
    solr_endpoint: str  # e.g., http://localhost:8983/solr/portal/select
) -> dict:
    """Execute a SOLR query and return the parsed JSON response."""

    # Merge base params (edismax config, highlighting, etc.) with custom params
    base_params = {
        "wt": "json",
        "defType": "edismax",
        "qf": "title^5 main_content heading_h1^3 ...",
        "pf": "main_content^5 title^8",
        # ... (see full config in solr.py lines 83-138)
    }
    base_params.update(params)

    logger.info("SOLR query: q=%r, fq=%r", params.get("q"), params.get("fq"))

    # ACTUAL HTTP REQUEST TO SOLR
    response = await client.get(solr_endpoint, params=base_params)
    response.raise_for_status()
    return response.json()
```

**Endpoint:** `{solr_url}/solr/portal/select`

**What it searches:**
- Full-length documents (not chunked)
- Fields: `title`, `main_content`, `heading_h1`, `heading_h2`, etc.
- Returns highlighted snippets from `main_content`

**Used by:**
- `tools.py:search_documentation()` - main search tool

---

## 4. RAG Searches (Chunked Document Search)

**File:** `src/okp_mcp/rag/common.py`

**Function:** `rag_query()` at line 123

```python
async def rag_query(
    endpoint: str,  # e.g., http://localhost:8984/solr/portal-rag/hybrid-search
    params: dict,
    client: httpx.AsyncClient
) -> RagResponse:
    """Execute a query against the portal-rag Solr core."""

    full_params = {"wt": "json"} | params
    logger.info("RAG query: endpoint=%r q=%r", endpoint, params.get("q"))

    # ACTUAL HTTP REQUEST TO SOLR
    response = await client.get(endpoint, params=full_params)
    response.raise_for_status()
    data = response.json()

    return _parse_solr_response(data)
```

**Endpoints (3 different RAG backends):**

### 4a. Hybrid Search
**File:** `src/okp_mcp/rag/hybrid.py`

```python
endpoint = f"{solr_url}/solr/portal-rag/hybrid-search"
params = {
    "q": query,
    "rows": max_results,
    "fq": "is_chunk:true",
    "bq": f'product:("{normalized_product}")^10'  # Product boost
}
```

**What it does:**
- Lexical search with server-side eDisMax config
- Field boosts: `title^30`, `chunk^20`, `headings_txt^15`
- Phrase boosting, recency bias, document-type weighting
- **This is where version filtering SHOULD be added!**

### 4b. Semantic Search
**File:** `src/okp_mcp/rag/semantic.py`

```python
endpoint = f"{solr_url}/solr/portal-rag/semantic-search"
params = {
    "q": "{!knn f=embedding_vector topK=100}[0.123, 0.456, ...]",  # Vector query
    "fq": "is_chunk:true",
    "rows": max_results,
}
```

**What it does:**
- Vector similarity search using KNN (k-nearest neighbors)
- Converts query to embedding vector using `Embedder`
- Searches `embedding_vector` field in Solr
- Returns chunks with highest cosine similarity

### 4c. Lexical Search
**File:** `src/okp_mcp/rag/lexical.py`

```python
endpoint = f"{solr_url}/solr/portal-rag/select"
params = {
    "q": query,
    "fq": "is_chunk:true",
    "rows": max_results,
    "defType": "edismax",
    "qf": "title chunk headings",
}
```

**What it does:**
- Basic edismax search without hybrid handler's server-side config
- Used as fallback or for debugging

### 4d. Portal Search (Solutions/Articles)
**File:** `src/okp_mcp/rag/portal.py`

```python
endpoint = f"{solr_url}/solr/portal-rag/portal-search"
params = {
    "q": query,
    "fq": "documentKind:(solution OR article)",
    "rows": max_results,
}
```

**What it does:**
- Searches only solutions and articles (not docs)
- Returns chunks from Red Hat Customer Portal content

---

## 5. How Searches Are Orchestrated

**File:** `src/okp_mcp/rag/tools.py`

**Function:** `_run_fused_search()` - runs 3 backends in parallel

```python
async def _run_fused_search(query: str, cleaned: str, *, app: AppContext, max_results: int, product: str):
    # Execute searches in parallel
    hybrid_coro = hybrid_search(cleaned, client=app.http_client, solr_url=app.rag_solr_url, ...)
    portal_coro = portal_search(cleaned, client=app.http_client, solr_url=app.rag_solr_url, ...)

    if app.embedder is not None:
        semantic_coro = semantic_text_search(query, embedder=app.embedder, ...)
        hybrid_result, semantic_result, portal_result = await asyncio.gather(
            hybrid_coro, semantic_coro, portal_coro, return_exceptions=True
        )
    else:
        hybrid_result, portal_result = await asyncio.gather(
            hybrid_coro, portal_coro, return_exceptions=True
        )
        semantic_result = None

    # Merge results with Reciprocal Rank Fusion (RRF)
    rag_results = [RagResponse(...), RagResponse(...), ...]
    return reciprocal_rank_fusion(*rag_results)
```

**Flow:**
1. Clean query (remove stopwords, quote hyphenated terms)
2. Run 3 searches in parallel:
   - Hybrid (lexical with server-side config)
   - Semantic (vector similarity, if embedder available)
   - Portal (solutions/articles)
3. Merge results with RRF (Reciprocal Rank Fusion)
4. Deduplicate chunks by parent_id
5. Expand contexts (fetch surrounding chunks)
6. Return top N results

---

## 6. Configuration for Different Environments

### Local Development (default)
```bash
# Uses localhost Solr instances
export MCP_SOLR_URL="http://localhost:8983"
export MCP_RAG_SOLR_URL="http://localhost:8984"
okp-mcp
```

### Docker Compose / Podman
**File:** `podman-compose.yml`

```yaml
services:
  redhat-okp:
    image: registry.redhat.io/offline-knowledge-portal/rhokp-rhel9:latest
    ports:
      - "8983:8983"
    environment:
      ACCESS_KEY: ${OKP_ACCESS_KEY}

  redhat-okp-rag:
    image: images.paas.redhat.com/offline-kbase/rhokp-rag:mar-9-2026
    ports:
      - "8984:8984"

  okp-mcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      MCP_SOLR_URL: http://redhat-okp:8983     # Container-to-container
      MCP_RAG_SOLR_URL: http://redhat-okp-rag:8984
    depends_on:
      - redhat-okp
```

**Start:**
```bash
podman-compose up -d
```

### OpenShift
**File:** `openshift/okp-mcp.yml`

```yaml
env:
  - name: MCP_SOLR_URL
    value: http://redhat-okp:8983
  - name: MCP_RAG_SOLR_URL
    value: http://redhat-okp-rag:8984
```

---

## 7. Solr Cores and What They Contain

### `portal` Core (Legacy)
**Accessed via:** `MCP_SOLR_URL/solr/portal/select`

**Content:**
- Full-length documents (not chunked)
- Red Hat documentation, solutions, articles, errata, CVEs
- Fields: `title`, `main_content`, `heading_h1`, `heading_h2`, `url`, `product`, `last_modified`

**Search Handler:** `/select` (standard Solr handler with edismax)

### `portal-rag` Core (RAG-optimized)
**Accessed via:** `MCP_RAG_SOLR_URL/solr/portal-rag/*`

**Content:**
- Chunked documents (split into ~500-token chunks)
- Same source content as `portal` but pre-processed for RAG
- Fields: `doc_id`, `parent_id`, `chunk`, `chunk_index`, `embedding_vector`, `product`, `product_version`

**Search Handlers:**
- `/hybrid-search` - Lexical search with server-side eDisMax config
- `/semantic-search` - Vector similarity search (KNN)
- `/portal-search` - Solutions/articles only
- `/select` - Standard handler

---

## 8. Where to Add Fixes (Based on Failing Questions Analysis)

### Fix #1: Add RHEL Version Filtering

**File:** `src/okp_mcp/rag/hybrid.py` (line 42-56)

**Current code:**
```python
endpoint = f"{solr_url}/solr/portal-rag/hybrid-search"
params = {
    "q": query,
    "rows": max_results,
    "fq": "is_chunk:true",
}
if product is not None:
    params["bq"] = f'product:("{normalized_product}")^10'  # Boost, not filter!
```

**Add version filtering:**
```python
params = {
    "q": query,
    "rows": max_results,
    "fq": ["is_chunk:true"],  # Make fq a list
}

# Extract RHEL version from query (e.g., "RHEL 10" → "10")
version_match = re.search(r'\bRHEL\s+(\d+)', query, re.IGNORECASE)
if version_match:
    version = int(version_match.group(1))
    # Hard filter: only this version and previous major version
    params["fq"].append(f'product_version:({version} OR {version - 1})')
    # Penalty for old versions
    params["bq"] = f'product_version:[5 TO 7]^0.1'
elif "rhel" in query.lower():
    # No version specified: default to current (10) and previous (9)
    params["fq"].append('product_version:(10 OR 9)')
    params["bq"] = f'product_version:[5 TO 7]^0.1'

if product is not None:
    if isinstance(params.get("bq"), list):
        params["bq"].append(f'product:("{normalized_product}")^10')
    else:
        params["bq"] = [params.get("bq", ""), f'product:("{normalized_product}")^10']
```

### Fix #2: De-boost Lifecycle Documents

**File:** `src/okp_mcp/rag/hybrid.py` (add to params)

```python
# Penalize lifecycle/policy docs unless explicitly requested
lifecycle_terms = ["life cycle", "lifecycle", "eol", "end of life", "support policy"]
if not any(term in query.lower() for term in lifecycle_terms):
    if "bq" not in params:
        params["bq"] = []
    params["bq"].append('url:(*life*cycle* OR *policy* OR *errata*)^0.2')
```

### Fix #3: Boost Technical Documentation

**File:** `src/okp_mcp/rag/hybrid.py` (add to params)

```python
# Boost installation guides, release notes, configuration docs
if "bq" not in params:
    params["bq"] = []
params["bq"].extend([
    'url:*installation*^3.0',
    'url:*release*notes*^3.0',
    'url:*configuring*^2.0',
    'url:*managing*^2.0',
    'title:"Installation Guide"^5.0',
    'title:"Release Notes"^4.0',
])
```

---

## 9. Testing Solr Connection

### Check if Solr is Running
```bash
# Main Solr instance
curl http://localhost:8983/solr/portal/admin/ping

# RAG Solr instance
curl http://localhost:8984/solr/portal-rag/admin/ping
```

### Manual Query (Main Portal)
```bash
curl "http://localhost:8983/solr/portal/select?q=DHCP&wt=json&rows=5" | jq '.response.docs[] | {title, url}'
```

### Manual Query (RAG Hybrid)
```bash
curl "http://localhost:8984/solr/portal-rag/hybrid-search?q=DHCP&rows=5&fq=is_chunk:true&wt=json" | jq '.response.docs[] | {title, chunk, product_version}'
```

### Check if okp-mcp Can Connect
```bash
# Start okp-mcp
okp-mcp --log-level DEBUG

# Watch logs for:
# "SOLR endpoint: http://localhost:8983/solr/portal/select"
# "RAG Solr URL: http://localhost:8984"
```

---

## 10. Troubleshooting

### "Connection refused" errors
**Problem:** Solr not running or wrong URL

**Solution:**
```bash
# Check if Solr containers are running
podman ps | grep okp

# Check Solr logs
podman logs redhat-okp
podman logs redhat-okp-rag

# Verify URLs in environment
env | grep MCP_
```

### "RAG tools disabled" in logs
**Problem:** `MCP_RAG_SOLR_URL` not set

**Solution:**
```bash
export MCP_RAG_SOLR_URL="http://localhost:8984"
okp-mcp
```

### Timeouts (30 seconds)
**Problem:** Solr query taking too long

**Solution:**
- Check Solr performance: `curl http://localhost:8983/solr/portal/admin/stats`
- Reduce `max_results` in queries
- Add more specific `fq` filters to narrow search

### Wrong results returned
**Problem:** Query returning irrelevant documents

**Check:**
1. Query cleaning: See what's sent to Solr in logs (`SOLR query: q=...`)
2. Solr response: Use manual curl query to see raw Solr results
3. Field boosts: Check `qf` parameters in `solr.py` line 90
4. Version filtering: Verify `product_version` field exists in Solr docs

---

## Summary

**Solr Connection Chain:**

```
config.py (defines MCP_SOLR_URL, MCP_RAG_SOLR_URL)
    ↓
server.py (creates httpx.AsyncClient, AppContext with URLs)
    ↓
tools.py (gets AppContext, passes to search functions)
    ↓
┌─────────────────┬────────────────────┐
│                 │                    │
solr.py           hybrid.py     semantic.py     portal.py
(legacy search)   (RAG hybrid)  (RAG vector)    (RAG portal)
    ↓                 ↓              ↓              ↓
common.py:rag_query() - Makes HTTP GET request
    ↓
httpx.AsyncClient.get(endpoint, params)
    ↓
Solr instance (8983 or 8984)
```

**Key Files:**
- `src/okp_mcp/config.py` - URL configuration
- `src/okp_mcp/server.py` - HTTP client setup
- `src/okp_mcp/solr.py` - Legacy portal search (line 143: actual HTTP call)
- `src/okp_mcp/rag/common.py` - RAG query executor (line 143: actual HTTP call)
- `src/okp_mcp/rag/hybrid.py` - Hybrid search endpoint builder
- `src/okp_mcp/rag/semantic.py` - Semantic search endpoint builder
- `src/okp_mcp/rag/tools.py` - Orchestrates multi-backend search

**To modify query behavior:** Edit `src/okp_mcp/rag/hybrid.py` lines 42-56 (params dict construction)

**To modify connection settings:** Set `MCP_SOLR_URL` and `MCP_RAG_SOLR_URL` environment variables
