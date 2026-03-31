# APIResponse Class Reference

## Overview

`APIResponse` is the **data model for raw API responses** from the LLM under test. It captures the complete API response including the answer, tool calls, contexts, and token usage. The evaluation pipeline automatically converts `APIResponse` to `TurnData` before passing to metrics.

**Location:** `src/lightspeed_evaluation/core/models/api.py`

**Purpose:** Bridge between API layer (HTTP responses) and evaluation layer (TurnData)

---

## When You'll Interact With APIResponse

| Scenario | Need to Understand APIResponse? |
|----------|--------------------------------|
| **Developing metrics** | ❌ No - use TurnData instead |
| **Writing evaluation configs** | ❌ No - use YAML structure |
| **Building test caches** | ✅ Yes - for cache key generation |
| **Debugging API integration** | ✅ Yes - understand response format |
| **Modifying API client** | ✅ Yes - core functionality |
| **Parsing tool call results** | ✅ Maybe - if customizing extraction |

**For most development work (95%): You can ignore this class and use TurnData.**

---

## Class Definition

```python
class APIResponse(StreamingMetricsMixin):
    """API response model."""
```

Inherits from `StreamingMetricsMixin` which adds:
- `time_to_first_token: Optional[float]` - Time to first token (seconds)
- `streaming_duration: Optional[float]` - Total streaming duration (seconds)
- `tokens_per_second: Optional[float]` - Token throughput (tokens/sec)

**Note:** Streaming metrics only populated when using `endpoint_type: streaming`

---

## Fields

### Core Response Data

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `response` | `str` | ✅ Yes | LLM's text response | `"Kea is the DHCP server in RHEL 10..."` |
| `conversation_id` | `str` | ✅ Yes | Conversation tracking ID | `"conv_12345_xyz"` |

### RAG and Tool Data

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `tool_calls` | `list[list[dict]]` | ❌ No | Tool call sequences | See structure below |
| `contexts` | `list[str]` | ❌ No | Extracted RAG contexts | `["Context 1", "Context 2"]` |

### Token Usage Tracking

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input_tokens` | `int` | ❌ No | Input tokens used (default: 0) |
| `output_tokens` | `int` | ❌ No | Output tokens used (default: 0) |

**Note:** These track the LLM being evaluated, NOT the judge LLM.

---

## Tool Calls Structure

`tool_calls` is a **list of sequences**, where each sequence is a list of tool call dictionaries.

### Format

```python
[
    [  # Sequence 1 (first round of tool calls)
        {
            "tool_name": "rag_fused_search",
            "arguments": {"query": "DHCP RHEL 10", "max_results": 5},
            "result": "## Result 1\nTitle: Installing Kea...\n---\n## Result 2..."
        },
        {
            "tool_name": "get_document",
            "arguments": {"doc_id": "/documentation/en-us/...", "query": "DHCP"},
            "result": "**Installing Kea DHCP Server**\nURL: https://..."
        }
    ],
    [  # Sequence 2 (second round, if LLM made follow-up tool calls)
        {
            "tool_name": "search_documentation",
            "arguments": {"query": "Kea configuration", "max_results": 3},
            "result": "..."
        }
    ]
]
```

### Field Details

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool_name` | `str` | ✅ Yes | Name of the tool called |
| `arguments` | `dict` | ✅ Yes | Arguments passed to tool (can be `{}`) |
| `result` | `str` | ❌ No | Tool execution result (if available) |

**Why sequences?** The LLM can make multiple rounds of tool calls (e.g., search → get_document → search again).

---

## Contexts Extraction

`contexts` are automatically extracted from `tool_calls` by parsing the `result` field.

### Extraction Logic (from APIResponse.from_raw_response)

```python
# Extract contexts from RAG chunks
raw_rag_chunks = raw_data.get("rag_chunks", [])
contexts = []
if raw_rag_chunks:
    for chunk_data in raw_rag_chunks:
        if isinstance(chunk_data, dict) and "content" in chunk_data:
            contexts.append(chunk_data["content"])
```

### Alternative: Tool Result Parsing

If RAG chunks aren't provided separately, contexts can be extracted from tool call results:

```python
# In client.py extract_contexts_from_tool_calls()
for sequence in tool_calls:
    for tool_call in sequence:
        if "result" in tool_call:
            # Parse "---" separated results
            result_text = tool_call["result"]
            sections = result_text.split("\n---\n")
            for section in sections:
                # Extract content after "Content:" or similar markers
                contexts.append(extract_content(section))
```

**See:** `src/lightspeed_evaluation/core/api/client.py` lines 310-330 for full logic.

---

## Factory Method: from_raw_response

Converts raw API JSON response to `APIResponse` object.

### Signature

```python
@classmethod
def from_raw_response(cls, raw_data: dict[str, Any]) -> "APIResponse":
    """Create APIResponse from raw API response data."""
```

### Input Format (Raw API JSON)

```json
{
  "response": "Kea is the DHCP server in RHEL 10...",
  "conversation_id": "conv_12345_xyz",
  "tool_calls": [
    [
      {
        "tool_name": "rag_fused_search",
        "arguments": {"query": "DHCP RHEL 10"},
        "result": "## Result 1\n..."
      }
    ]
  ],
  "rag_chunks": [
    {"content": "Kea DHCP server is...", "source": "docs.redhat.com/...", "score": 0.95},
    {"content": "RHEL 10 uses Kea...", "source": "access.redhat.com/...", "score": 0.87}
  ],
  "input_tokens": 150,
  "output_tokens": 250,
  "time_to_first_token": 0.45,
  "streaming_duration": 2.3,
  "tokens_per_second": 108.7
}
```

### Processing Steps

1. **Validate required fields**
   ```python
   conversation_id = raw_data.get("conversation_id")
   if not conversation_id:
       raise ValueError("conversation_id is required in API response")
   ```

2. **Extract tool calls**
   ```python
   tool_call_sequences = raw_data.get("tool_calls", [])
   ```

3. **Extract contexts from RAG chunks**
   ```python
   raw_rag_chunks = raw_data.get("rag_chunks", [])
   contexts = [chunk["content"] for chunk in raw_rag_chunks if "content" in chunk]
   ```

4. **Extract token counts**
   ```python
   input_tokens = raw_data.get("input_tokens", 0)
   output_tokens = raw_data.get("output_tokens", 0)
   ```

5. **Extract streaming metrics (if available)**
   ```python
   time_to_first_token = raw_data.get("time_to_first_token")
   streaming_duration = raw_data.get("streaming_duration")
   tokens_per_second = raw_data.get("tokens_per_second")
   ```

6. **Create APIResponse object**
   ```python
   return cls(
       response=raw_data["response"].strip(),
       conversation_id=conversation_id,
       tool_calls=tool_call_sequences,
       contexts=contexts,
       input_tokens=input_tokens,
       output_tokens=output_tokens,
       time_to_first_token=time_to_first_token,
       streaming_duration=streaming_duration,
       tokens_per_second=tokens_per_second,
   )
   ```

---

## Conversion to TurnData

The evaluation pipeline converts `APIResponse` → `TurnData` automatically.

### Mapping

| APIResponse Field | → | TurnData Field |
|-------------------|---|----------------|
| `response` | → | `response` |
| `tool_calls` | → | `tool_calls` |
| `contexts` | → | `contexts` |
| `conversation_id` | → | `conversation_id` |
| `input_tokens` | → | `api_input_tokens` |
| `output_tokens` | → | `api_output_tokens` |
| `time_to_first_token` | → | `time_to_first_token` |
| `streaming_duration` | → | `streaming_duration` |
| `tokens_per_second` | → | `tokens_per_second` |

**Note:** `TurnData` also has fields that don't come from `APIResponse` (e.g., `expected_response`, `expected_keywords`) - those come from the YAML config.

---

## Caching

`APIResponse` objects are cached using `diskcache.Cache` to avoid redundant API calls.

### Cache Key Generation

**From:** `src/lightspeed_evaluation/core/api/client.py`

```python
def _get_cache_key(self, request: APIRequest) -> str:
    """Get cache key for the query."""
    request_dict = request.model_dump()
    keys_to_hash = [
        "query",
        "provider",
        "model",
        "no_tools",
        "system_prompt",
        "attachments",
    ]
    str_request = ",".join([str(request_dict[k]) for k in keys_to_hash])
    return hashlib.sha256(str_request.encode()).hexdigest()
```

### Cache Storage

**Location:** `.caches/api_cache/` (configurable in `system.yaml`)

**Format:** Pickled `APIResponse` objects indexed by SHA256 hash

### Cache Behavior

**On cache hit:**
```python
cached_response = self.cache.get(cache_key)
if cached_response is not None:
    # Zero out token counts (no API call made)
    cached_response.input_tokens = 0
    cached_response.output_tokens = 0
    return cached_response
```

**On cache miss:**
```python
response = make_api_call(request)
self.cache[cache_key] = response
return response
```

---

## Building Test Caches

This is the **primary reason you'd manually create APIResponse objects** - to populate caches for testing without making real API calls.

### Example: Building a Test Cache

```python
from diskcache import Cache
from lightspeed_evaluation.core.models.api import APIResponse
import hashlib

# Initialize cache
cache = Cache(".caches/test_cache")

# Create APIResponse manually
api_response = APIResponse(
    response="Kea is the DHCP server in RHEL 10. Install with: dnf install kea",
    conversation_id="test-12345",
    tool_calls=[
        [
            {
                "tool_name": "rag_fused_search",
                "arguments": {"query": "DHCP RHEL 10"},
                "result": "## Result 1\nTitle: Installing Kea DHCP\nContent: Kea is..."
            }
        ]
    ],
    contexts=[
        "Kea is the DHCP server in RHEL 10",
        "ISC DHCP was removed in RHEL 10"
    ],
    input_tokens=0,  # Zeroed for cached responses
    output_tokens=0,
)

# Generate cache key (must match what client.py generates!)
# IMPORTANT: These values must match config/system.yaml
request_parts = [
    "How to install Kea DHCP on RHEL 10?",  # query
    "vertex",                                # provider (from system.yaml)
    "google/gemini-2.5-flash",              # model (from system.yaml)
    "None",                                  # no_tools
    "None",                                  # system_prompt
    "None",                                  # attachments
]
str_request = ",".join(request_parts)
cache_key = hashlib.sha256(str_request.encode()).hexdigest()

# Store in cache
cache[cache_key] = api_response

print(f"Cached response with key: {cache_key}")
cache.close()
```

**Critical:** The cache key must exactly match what `client.py` generates, or the cache won't be used!

---

## Related Classes

### RAGChunk

```python
class RAGChunk(BaseModel):
    """RAG chunk data from lightspeed-stack API."""

    content: str = Field(..., description="RAG chunk content")
    source: str = Field(..., description="Source of the RAG chunk")
    score: Optional[float] = Field(default=None, description="Relevance score")
```

**Used by:** API to return RAG search results
**Extracted to:** `APIResponse.contexts`

### AttachmentData

```python
class AttachmentData(BaseModel):
    """Individual attachment structure for API."""

    attachment_type: str = Field(default="configuration")
    content: str = Field(...)
    content_type: str = Field(default="text/plain")
```

**Used by:** `APIRequest` when sending file attachments to LLM

---

## Common Patterns

### Pattern 1: Parsing Tool Results in Custom Code

```python
def extract_urls_from_tool_calls(api_response: APIResponse) -> list[str]:
    """Extract all URLs from tool call results."""
    urls = []
    for sequence in api_response.tool_calls:
        for tool_call in sequence:
            result = tool_call.get("result", "")
            # Parse URLs from result
            urls.extend(re.findall(r'https?://[^\s]+', result))
    return urls
```

### Pattern 2: Validating Response Format

```python
def validate_api_response(api_response: APIResponse) -> tuple[bool, str]:
    """Validate APIResponse has required data."""
    if not api_response.response:
        return False, "Missing response text"

    if not api_response.conversation_id:
        return False, "Missing conversation_id"

    if not api_response.contexts:
        return False, "No contexts retrieved"

    return True, "Valid response"
```

### Pattern 3: Building Fake APIResponse for Testing

```python
def create_test_response(
    question: str,
    answer: str,
    contexts: list[str],
) -> APIResponse:
    """Create a fake APIResponse for testing."""
    return APIResponse(
        response=answer,
        conversation_id=f"test-{hashlib.md5(question.encode()).hexdigest()[:8]}",
        tool_calls=[
            [
                {
                    "tool_name": "search_documentation",
                    "arguments": {"query": question},
                    "result": "\n---\n".join(contexts)
                }
            ]
        ],
        contexts=contexts,
        input_tokens=0,
        output_tokens=0,
    )
```

---

## Debugging Tips

### Problem: Cache Not Being Used

**Symptom:** API calls made even though cache exists

**Check:**
1. Cache key generation matches exactly
   ```python
   # Log cache key in your test
   print(f"Cache key: {cache_key}")

   # Log cache key in client.py (add debug logging)
   logger.debug(f"Looking up cache key: {cache_key}")
   ```

2. Provider/model match `system.yaml`
   ```yaml
   api:
     provider: "vertex"          # Must match exactly!
     model: "google/gemini-2.5-flash"  # Must match exactly!
   ```

3. Cache directory exists and is readable
   ```bash
   ls -la .caches/api_cache/
   ```

### Problem: Contexts Not Extracted

**Symptom:** `APIResponse.contexts` is empty even though tool calls have results

**Check:**
1. RAG chunks format
   ```python
   # Verify rag_chunks in raw response
   print(raw_data.get("rag_chunks"))
   ```

2. Tool result parsing
   ```python
   # Check if result field exists
   for seq in api_response.tool_calls:
       for tool in seq:
           print(f"Tool: {tool['tool_name']}, Has result: {'result' in tool}")
   ```

### Problem: Token Counts Wrong

**Symptom:** Token counts don't match expected values

**Check:**
1. Cached responses have zeroed tokens (expected)
   ```python
   if cached_response:
       # Tokens are zeroed because no API call made
       assert cached_response.input_tokens == 0
       assert cached_response.output_tokens == 0
   ```

2. Live API responses have correct token counts
   ```python
   # Check raw API response
   print(f"Input tokens: {raw_data.get('input_tokens')}")
   print(f"Output tokens: {raw_data.get('output_tokens')}")
   ```

---

## Comparison: APIResponse vs TurnData

| Aspect | APIResponse | TurnData |
|--------|-------------|----------|
| **Purpose** | Raw API response | Evaluation input |
| **Source** | API call | APIResponse + YAML config |
| **Contains** | Actual data only | Actual + Expected data |
| **Used by** | API client, Pipeline | Metrics |
| **When to use** | Building caches, API debugging | Developing metrics |
| **Fields** | 6 core fields | 20+ fields |
| **Validation** | Basic (required fields) | Extensive (ground truth) |

---

## Summary

**APIResponse in a Nutshell:**
- 📦 Container for raw API responses
- 🔄 Automatically converted to TurnData
- 💾 Used for caching to avoid redundant API calls
- 🛠️ Rarely needed for metric development

**When You Care:**
- ✅ Building test caches
- ✅ Debugging API integration
- ✅ Modifying API client
- ❌ Developing metrics (use TurnData)
- ❌ Writing configs (use YAML)

**Key Takeaway:** For 95% of development work, you can ignore `APIResponse` and work with `TurnData` instead. Only worry about `APIResponse` when dealing with caching or API layer debugging.
