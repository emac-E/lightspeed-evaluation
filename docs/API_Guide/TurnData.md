# TurnData Class Reference

## Overview

`TurnData` is the **primary data model for metric evaluation** in the lightspeed-evaluation framework. When developing custom metrics, this is the only class you need to understand - it contains all the information required to evaluate a single turn (question/answer pair) in a conversation.

**Location:** `src/lightspeed_evaluation/core/models/data.py`

**Purpose:** Represents a single question-answer exchange with all necessary data for evaluation (query, response, contexts, expected values, token counts, etc.)

---

## Key Concept

```
APIResponse (from API call)
    ↓ Pipeline automatically converts
TurnData (what metrics receive)
    ↓ Your metric evaluates
(score, reason) tuple
```

**You only work with TurnData when developing metrics.**

---

## Class Definition

```python
class TurnData(StreamingMetricsMixin):
    """Individual turn data within a conversation."""
```

Inherits from `StreamingMetricsMixin` which adds:
- `time_to_first_token: Optional[float]` - Time to first token (streaming only)
- `streaming_duration: Optional[float]` - Total streaming time (streaming only)
- `tokens_per_second: Optional[float]` - Token throughput (streaming only)

---

## Core Fields (Always Used)

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `turn_id` | `str` | Unique identifier for this turn | `"turn1"`, `"RSPEED-1998"` |
| `query` | `str` | User's question or input | `"How to install Kea DHCP on RHEL 10?"` |

### Actual Data (Populated by API or Pre-filled)

| Field | Type | Description | When Populated |
|-------|------|-------------|----------------|
| `response` | `Optional[str]` | LLM's answer | API call or pre-filled in YAML |
| `tool_calls` | `Optional[list[list[dict]]]` | Tools the LLM called | API call or pre-filled in YAML |
| `contexts` | `Optional[list[str]]` | Retrieved RAG contexts | Extracted from tool calls or pre-filled |
| `conversation_id` | `Optional[str]` | Conversation tracking ID | API call |

**Structure of `tool_calls`:**
```python
[
    [  # Sequence 1
        {"tool_name": "rag_fused_search", "arguments": {"query": "..."}, "result": "..."},
        {"tool_name": "get_document", "arguments": {"doc_id": "..."}, "result": "..."}
    ],
    [  # Sequence 2 (if LLM made multiple tool call rounds)
        {"tool_name": "search_documentation", "arguments": {...}}
    ]
]
```

---

## Expected Values (Ground Truth)

These fields define what the correct answer should look like. Used by metrics to evaluate quality.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `expected_response` | `Optional[Union[str, list[str]]]` | What the answer should say | `"Kea is the DHCP server in RHEL 10"` or `["Answer 1", "Answer 2"]` |
| `expected_keywords` | `Optional[list[list[str]]]` | Required keywords (with alternatives) | `[["Kea", "kea"], ["RHEL 10"]]` |
| `expected_tool_calls` | `Optional[list[list[list[dict]]]]` | Expected tools to call | See Tool Calls section below |
| `expected_intent` | `Optional[str]` | Expected user intent | `"Install DHCP server on RHEL 10"` |

**Example `expected_keywords` (alternatives):**
```python
[
    ["Kea", "kea"],           # Alternative 1: Must contain "Kea" OR "kea"
    ["RHEL 10", "RHEL10"],    # Alternative 2: Must contain "RHEL 10" OR "RHEL10"
    ["dnf install", "yum install"]  # Alternative 3: Must contain one of these
]
# Evaluation: ALL alternatives must be satisfied (at least one keyword from each group)
```

**Example `expected_response` (multiple acceptable answers):**
```python
expected_response = [
    "Kea is the DHCP server in RHEL 10. Install with: dnf install kea",
    "RHEL 10 uses Kea DHCP server instead of ISC DHCP",
    "Use Kea for DHCP in RHEL 10"
]
# Evaluation: Response matches ANY of these answers
```

---

## Token Tracking

| Field | Type | Description |
|-------|------|-------------|
| `api_input_tokens` | `int` | Tokens used for API request (default: 0) |
| `api_output_tokens` | `int` | Tokens used for API response (default: 0) |

**Note:** These track the LLM being evaluated (not the judge LLM). Judge LLM tokens are in `MetricResult`.

---

## Metric Configuration

| Field | Type | Description |
|-------|------|-------------|
| `turn_metrics` | `Optional[list[str]]` | Metrics to run for this turn (overrides system defaults) |
| `turn_metrics_metadata` | `Optional[dict[str, dict]]` | Metric-specific config (overrides system defaults) |

**Example:**
```yaml
turn_metrics:
  - ragas:faithfulness
  - ragas:context_recall
  - custom:answer_correctness

turn_metrics_metadata:
  ragas:faithfulness:
    threshold: 0.9
  custom:answer_correctness:
    threshold: 0.75
```

---

## Script Execution

| Field | Type | Description |
|-------|------|-------------|
| `verify_script` | `Optional[Union[str, Path]]` | Path to script that validates environment/infrastructure |

**Example:**
```yaml
verify_script: "tests/scripts/verify_dhcp_installed.sh"
```

The script runs and returns:
- Exit code 0 = PASS
- Exit code != 0 = FAIL
- stdout/stderr captured for debugging

---

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `attachments` | `Optional[list[str]]` | File attachments (e.g., config files, logs) |

---

## Expected Tool Calls Structure

`expected_tool_calls` supports **alternative sets** to allow flexibility in tool calling patterns.

### Format

```python
[
    [  # Alternative Set 1 (preferred)
        [  # Sequence 1
            {"tool_name": "rag_fused_search", "arguments": {"query": "DHCP RHEL 10"}},
            {"tool_name": "get_document", "arguments": {"doc_id": "/documentation/..."}}
        ]
    ],
    [  # Alternative Set 2 (acceptable alternative)
        [  # Sequence 1
            {"tool_name": "search_documentation", "arguments": {"query": "DHCP"}}
        ]
    ],
    []  # Alternative Set 3 (fallback: no tools called - LLM uses parametric knowledge)
]
```

**Evaluation logic:**
- If actual tool calls match **ANY** alternative set → PASS
- Order matters (unless `ordered: false` in metadata)
- Exact match required (unless `full_match: false` in metadata)

### Validation Rules

1. **Empty sequences not allowed** (use `[]` for empty alternative)
   ```python
   # ❌ INVALID
   [[]]  # Empty sequence

   # ✅ VALID
   []    # Empty alternative (no tools)
   ```

2. **Empty alternatives must come last**
   ```python
   # ❌ INVALID
   [[], [[tool1]]]  # Empty first

   # ✅ VALID
   [[[tool1]], []]  # Empty last
   ```

3. **Required fields:** `tool_name` (required), `arguments` (optional, defaults to `{}`)

---

## Internal Methods (Not for Metric Development)

| Method | Purpose |
|--------|---------|
| `add_invalid_metric(metric: str)` | Mark metric as invalid during validation |
| `is_metric_invalid(metric: str)` | Check if metric failed validation |
| `validate_turn_metrics(v)` | Validator for turn_metrics field |
| `validate_expected_response(v)` | Validator for expected_response field |
| `validate_expected_keywords(v)` | Validator for expected_keywords field |
| `validate_expected_tool_calls(v)` | Validator for expected_tool_calls field |

**You don't call these - the framework handles validation automatically.**

---

## Usage in Metric Development

### Basic Metric Example

```python
def _evaluate_response_length(
    self,
    _conv_data: Any,
    _turn_idx: Optional[int],
    turn_data: Optional[TurnData],
    is_conversation: bool,
) -> tuple[Optional[float], str]:
    """Evaluate if response has appropriate length."""
    # Check scope
    if is_conversation:
        return None, "Response length is a turn-level metric"

    if turn_data is None or not turn_data.response:
        return None, "No response to evaluate"

    # Access TurnData fields
    word_count = len(turn_data.response.split())

    # Evaluate
    if 50 <= word_count <= 300:
        return 1.0, f"Good length: {word_count} words"
    elif word_count < 50:
        return 0.5, f"Too short: {word_count} words"
    else:
        return 0.3, f"Too verbose: {word_count} words"
```

### Accessing All Available Data

```python
def _evaluate_custom_metric(
    self,
    _conv_data: Any,
    _turn_idx: Optional[int],
    turn_data: Optional[TurnData],
    is_conversation: bool,
) -> tuple[Optional[float], str]:
    """Example showing all TurnData fields you can access."""
    if turn_data is None:
        return None, "No turn data"

    # Core fields
    question = turn_data.query
    answer = turn_data.response
    turn_id = turn_data.turn_id

    # RAG contexts (if available)
    contexts = turn_data.contexts or []

    # Expected values (ground truth)
    expected = turn_data.expected_response
    expected_keywords = turn_data.expected_keywords

    # Tool calls
    tools_called = turn_data.tool_calls or []
    expected_tools = turn_data.expected_tool_calls or []

    # Token usage
    input_tokens = turn_data.api_input_tokens
    output_tokens = turn_data.api_output_tokens

    # Streaming metrics (if using streaming endpoint)
    ttft = turn_data.time_to_first_token
    duration = turn_data.streaming_duration
    tps = turn_data.tokens_per_second

    # Your evaluation logic here
    score = evaluate_somehow(question, answer, contexts, expected)

    return score, f"Evaluation reason for {turn_id}"
```

---

## Common Patterns

### Pattern 1: Evaluating Against Ground Truth

```python
def _evaluate_answer_correctness(self, ..., turn_data: TurnData, ...) -> tuple[float, str]:
    query = turn_data.query
    response = turn_data.response
    expected = turn_data.expected_response

    # Use LLM to compare response vs expected
    prompt = f"Does this answer '{response}' match the expected '{expected}'?"
    llm_result = self.llm.call(prompt)

    return parse_score(llm_result)
```

### Pattern 2: Checking RAG Context Quality

```python
def _evaluate_context_relevance(self, ..., turn_data: TurnData, ...) -> tuple[float, str]:
    query = turn_data.query
    contexts = turn_data.contexts or []

    if not contexts:
        return 0.0, "No contexts retrieved"

    # Calculate how many contexts are relevant
    relevant_count = sum(1 for ctx in contexts if is_relevant(query, ctx))
    score = relevant_count / len(contexts)

    return score, f"{relevant_count}/{len(contexts)} contexts relevant"
```

### Pattern 3: Validating Tool Calls

```python
def _evaluate_tool_calls(self, ..., turn_data: TurnData, ...) -> tuple[float, str]:
    actual_tools = turn_data.tool_calls or []
    expected_tools = turn_data.expected_tool_calls or []

    if not expected_tools:
        return None, "No expected tool calls defined"

    # Check if actual matches any alternative set
    for alt_set in expected_tools:
        if matches(actual_tools, alt_set):
            return 1.0, "Tool calls match expected pattern"

    return 0.0, "Tool calls don't match any expected pattern"
```

### Pattern 4: Keyword Validation

```python
def _evaluate_keywords(self, ..., turn_data: TurnData, ...) -> tuple[float, str]:
    response = turn_data.response or ""
    keyword_groups = turn_data.expected_keywords or []

    if not keyword_groups:
        return None, "No keywords defined"

    missing_groups = []
    for i, group in enumerate(keyword_groups):
        # Check if ANY keyword from this group is present
        if not any(kw.lower() in response.lower() for kw in group):
            missing_groups.append(f"Group {i}: {group}")

    if missing_groups:
        return 0.0, f"Missing keywords: {', '.join(missing_groups)}"

    return 1.0, "All keyword groups found"
```

---

## YAML Configuration Example

```yaml
- conversation_group_id: EXAMPLE-001
  description: "Example conversation showing all TurnData fields"
  tag: examples

  turns:
    - turn_id: turn1
      query: "How to install Kea DHCP on RHEL 10?"

      # Actual data (populated by API if enabled: true)
      response: null  # Will be filled by API call
      tool_calls: null  # Will be filled by API call
      contexts: null  # Will be extracted from tool calls

      # Expected values (ground truth)
      expected_response: |
        Kea is the DHCP server in RHEL 10. ISC DHCP was removed.
        Installation: dnf install kea
        Configuration: /etc/kea/kea-dhcp4.conf

      expected_keywords:
        - ["Kea", "kea"]
        - ["RHEL 10"]
        - ["dnf install"]

      expected_tool_calls:
        - [  # Alternative 1: Use RAG search
            [
              {"tool_name": "rag_fused_search", "arguments": {"query": "Kea DHCP RHEL 10"}}
            ]
          ]
        - [  # Alternative 2: Use documentation search
            [
              {"tool_name": "search_documentation", "arguments": {"query": "DHCP RHEL 10"}}
            ]
          ]

      # Metrics to run
      turn_metrics:
        - ragas:faithfulness
        - ragas:context_recall
        - custom:answer_correctness

      turn_metrics_metadata:
        ragas:faithfulness:
          threshold: 0.85
        custom:answer_correctness:
          threshold: 0.75

      # Optional: Script-based validation
      verify_script: "tests/scripts/verify_kea_installed.sh"
```

---

## Best Practices

### 1. Always Check for None

```python
# ✅ GOOD
if turn_data is None or not turn_data.response:
    return None, "No response to evaluate"

# ❌ BAD (will crash if response is None)
word_count = len(turn_data.response.split())
```

### 2. Provide Default Values for Optional Fields

```python
# ✅ GOOD
contexts = turn_data.contexts or []
tool_calls = turn_data.tool_calls or []

# ❌ BAD (will crash if contexts is None)
for context in turn_data.contexts:
    process(context)
```

### 3. Return Descriptive Reasons

```python
# ✅ GOOD
return 0.75, "Answer is 75% correct: mentions Kea but missing configuration details"

# ❌ BAD (not helpful for debugging)
return 0.75, "Score: 0.75"
```

### 4. Handle Missing Ground Truth Gracefully

```python
# ✅ GOOD
if not turn_data.expected_response:
    return None, "No expected response defined - cannot evaluate"

# ❌ BAD (crashes or gives misleading results)
score = compare(turn_data.response, turn_data.expected_response)
```

---

## Summary

**For Metric Development:**
- ✅ Use `TurnData` - it has everything you need
- ❌ Ignore `APIRequest` and `APIResponse` - those are for API layer

**Key Fields to Remember:**
- `query` - the question
- `response` - the answer
- `contexts` - RAG contexts
- `expected_response` - ground truth
- `tool_calls` - what tools were called

**Common Use Cases:**
1. Compare response vs expected_response → `custom:answer_correctness`
2. Check if contexts contain answer → `ragas:context_recall`
3. Validate tool calls → `custom:tool_eval`
4. Check for keywords → `custom:keywords_eval`

That's it! Everything else is handled by the framework automatically.
