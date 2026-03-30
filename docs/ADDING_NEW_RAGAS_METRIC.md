# How to Add a New Ragas Metric

This guide explains the complete flow of how ragas metrics work and how to add a new one.

---

## The Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. CONFIGURATION FILES                                          │
└─────────────────────────────────────────────────────────────────┘

config/system.yaml                    config/your_tests.yaml
─────────────────                     ──────────────────────
metrics_metadata:                     turns:
  turn_level:                           - query: "..."
    "ragas:YOUR_METRIC":      ────────►   turn_metrics:
      threshold: 0.7                        - ragas:YOUR_METRIC
      description: "..."
      default: false

       │                                            │
       │ Loaded by                                  │ Loaded by
       ▼                                            ▼

┌─────────────────────────────────────────────────────────────────┐
│ 2. SYSTEM INITIALIZATION                                        │
└─────────────────────────────────────────────────────────────────┘

SystemConfig (models/system.py)
────────────────────────────────
- Parses system.yaml
- Stores metrics_metadata.turn_level as dict
- Available via: system_config.default_turn_metrics_metadata

       │
       │ Passed to
       ▼

MetricManager (core/metrics/manager.py)
────────────────────────────────────────
- Resolves which metrics to run (None → defaults, [] → skip, list → use list)
- Gets threshold from metadata
- Validates metric availability

       │
       │ Used by
       ▼

┌─────────────────────────────────────────────────────────────────┐
│ 3. METRIC EXECUTION                                             │
└─────────────────────────────────────────────────────────────────┘

Evaluator (pipeline/evaluation/evaluator.py)
─────────────────────────────────────────────
For each turn:
  1. Get metric list from turn_metrics field
  2. Parse "ragas:YOUR_METRIC" → provider="ragas", name="YOUR_METRIC"
  3. Route to RagasMetrics class

       │
       │ Calls
       ▼

RagasMetrics (core/metrics/ragas.py)
─────────────────────────────────────
supported_metrics = {
    "YOUR_METRIC": self._evaluate_YOUR_METRIC,
}

def _evaluate_YOUR_METRIC(self, ...):
    # Extract data
    query, response, contexts = self._extract_turn_data(turn_data)

    # Build dataset
    dataset_dict = {
        "question": [query],
        "answer": [response],
        "contexts": [contexts],
    }

    # Call ragas library
    return self._evaluate_metric(
        YourRagasClass,  # From ragas.metrics import
        {},              # Extra kwargs
        dataset_dict,
        "result_key",    # Column name in ragas output
        "YOUR_METRIC"
    )

       │
       │ Uses
       ▼

ragas library (ragas.metrics)
──────────────────────────────
- YourRagasClass.evaluate(dataset)
- Returns DataFrame with scores
- Scores extracted and returned

       │
       │ Results flow back
       ▼

┌─────────────────────────────────────────────────────────────────┐
│ 4. RESULTS PROCESSING                                           │
└─────────────────────────────────────────────────────────────────┘

Evaluator
──────────
- Gets (score, reason) tuple
- Compares score to threshold
- Determines PASS/FAIL/ERROR

       │
       │ Saved to
       ▼

OutputHandler (core/output/handler.py)
───────────────────────────────────────
Generates:
- CSV: evaluation_TIMESTAMP_detailed.csv
- JSON: evaluation_TIMESTAMP_summary.json
- TXT: evaluation_TIMESTAMP_summary.txt
```

---

## Step-by-Step: Adding a New Ragas Metric

### Example: Adding `ragas:noise_sensitivity`

#### Step 1: Add to system.yaml

```yaml
# config/system.yaml
metrics_metadata:
  turn_level:
    "ragas:noise_sensitivity":
      threshold: 0.7
      description: "Measures how much noise affects the LLM's ability to answer correctly"
      default: false  # Don't apply by default
```

**What this does:**
- Registers the metric in the system
- Sets default threshold (0.7)
- Makes it available for use in test files
- `default: false` means it only runs when explicitly requested

---

#### Step 2: Import the ragas class

```python
# src/lightspeed_evaluation/core/metrics/ragas.py

# Add to imports at top of file
from ragas.metrics import (
    ContextRelevance,
    Faithfulness,
    # ... existing imports ...
    NoiseSensitivity,  # ← ADD THIS (or whatever the actual class name is)
)
```

**How to find the class name:**
```bash
# Check what's available in ragas
python -c "from ragas import metrics; print(dir(metrics))"

# Or check ragas documentation
# https://docs.ragas.io/en/latest/concepts/metrics/
```

---

#### Step 3: Register in supported_metrics dict

```python
# src/lightspeed_evaluation/core/metrics/ragas.py

class RagasMetrics:
    def __init__(self, llm_manager: LLMManager, embedding_manager: EmbeddingManager):
        # ... existing code ...

        self.supported_metrics = {
            # Response evaluation metrics
            "faithfulness": self._evaluate_faithfulness,
            "response_relevancy": self._evaluate_response_relevancy,
            # Context/Retrieval evaluation metrics
            "context_recall": self._evaluate_context_recall,
            "context_relevance": self._evaluate_context_relevance,
            "context_precision_with_reference": self._evaluate_context_precision_with_reference,
            "context_precision_without_reference": (
                self._evaluate_context_precision_without_reference
            ),
            # ← ADD YOUR METRIC HERE
            "noise_sensitivity": self._evaluate_noise_sensitivity,
        }
```

**Key points:**
- The key (`"noise_sensitivity"`) must match what comes after `ragas:` in your test YAML
- The value is a method you'll create in the next step

---

#### Step 4: Implement the evaluation method

```python
# src/lightspeed_evaluation/core/metrics/ragas.py

def _evaluate_noise_sensitivity(
    self,
    _conv_data: Any,
    _turn_idx: Optional[int],
    turn_data: Optional[TurnData],
    is_conversation: bool,
) -> tuple[Optional[float], str]:
    """Evaluate noise sensitivity.

    Measures how robust the LLM's answer is when noise is added to contexts.
    """
    # Step 1: Check if this is the right level
    if is_conversation:
        return None, "Noise sensitivity is a turn-level metric"

    # Step 2: Extract data from turn
    query, response, contexts = self._extract_turn_data(turn_data)

    # Step 3: Build dataset dict
    # (Check ragas docs for what fields your metric needs)
    dataset_dict = {
        "question": [query],
        "answer": [response],
        "contexts": [contexts],
    }

    # Step 4: Call the generic evaluator
    return self._evaluate_metric(
        NoiseSensitivity,        # ← The ragas class you imported
        {},                      # ← Extra kwargs (if metric needs them)
        dataset_dict,           # ← Data for evaluation
        "noise_sensitivity",     # ← Column name in ragas output DataFrame
        "noise sensitivity"      # ← Human-readable name for logging
    )
```

**Important notes:**

1. **Method signature:** Must match exactly (takes these 4 params)
2. **is_conversation check:** Most ragas metrics are turn-level (per question)
3. **dataset_dict keys:** Must match what ragas expects:
   - Check ragas docs for your specific metric
   - Common keys: `question`, `answer`, `contexts`, `ground_truth`
4. **result_key:** The column name ragas uses in its output DataFrame
   - Find this by reading ragas source code or docs
   - Example: `faithfulness` returns column "faithfulness"
   - Example: `context_precision_without_reference` returns "llm_context_precision_without_reference"

---

#### Step 5: Use it in your test YAML

```yaml
# config/your_test.yaml

- conversation_group_id: NOISE-TEST-001
  description: "Test noise sensitivity metric"
  tag: noise_test

  turns:
    - turn_id: turn1
      query: "How to install DHCP in RHEL 10?"
      response: null
      contexts: null

      expected_response: |
        Install Kea DHCP in RHEL 10...

      turn_metrics:
        - ragas:noise_sensitivity  # ← YOUR NEW METRIC
        - ragas:faithfulness
        - custom:answer_correctness
```

**Result:**
- Metric will run for this turn
- Score compared to threshold from system.yaml (0.7)
- Output in CSV: "ragas:noise_sensitivity", score, PASS/FAIL

---

## What Fields Does My Metric Need?

Different ragas metrics require different fields. Here's a quick reference:

### Response Metrics

```python
# response_relevancy
dataset_dict = {
    "question": [query],
    "answer": [response],
}

# faithfulness
dataset_dict = {
    "question": [query],
    "answer": [response],
    "contexts": [contexts],
}
```

### Context Metrics

```python
# context_relevance
dataset_dict = {
    "question": [query],
    "contexts": [contexts],
}

# context_precision_without_reference
dataset_dict = {
    "question": [query],
    "answer": [response],
    "contexts": [contexts],
}

# context_precision_with_reference (needs expected answer)
dataset_dict = {
    "question": [query],
    "answer": [response],
    "contexts": [contexts],
    "ground_truth": [turn_data.expected_response],
}

# context_recall (needs expected answer)
dataset_dict = {
    "question": [query],
    "answer": [response],
    "contexts": [contexts],
    "ground_truth": [turn_data.expected_response],
}
```

**How to find what your metric needs:**
1. Check ragas documentation
2. Look at ragas source code for your metric class
3. Try it and see what error you get (will tell you missing fields)

---

## Passing Extra Parameters to Ragas

Some metrics accept configuration parameters:

```python
def _evaluate_your_metric(self, ...):
    # ...

    return self._evaluate_metric(
        YourMetricClass,
        {
            "param1": "value1",    # ← Pass extra params here
            "param2": 42,
        },
        dataset_dict,
        "result_key",
        "metric name"
    )
```

Example from response_relevancy:
```python
return self._evaluate_metric(
    ResponseRelevancy,
    {"embeddings": self.embedding_manager.embeddings},  # ← Needs embeddings
    dataset_dict,
    "answer_relevancy",
    "response relevancy",
)
```

---

## Debugging Tips

### 1. Check if metric is registered

```python
# In Python console
from lightspeed_evaluation.core.metrics.ragas import RagasMetrics
from lightspeed_evaluation.core.llm.manager import LLMManager
from lightspeed_evaluation.core.embedding.manager import EmbeddingManager

# Create instance (with dummy config)
ragas_metrics = RagasMetrics(llm_manager, embedding_manager)
print(ragas_metrics.supported_metrics.keys())
# Should see your metric name
```

### 2. Check ragas output column name

```python
# Run metric manually to see output
from ragas import evaluate
from ragas.metrics import YourMetricClass
from datasets import Dataset

dataset = Dataset.from_dict({
    "question": ["test"],
    "answer": ["test"],
    "contexts": [["test"]],
})

result = evaluate(dataset, metrics=[YourMetricClass()])
print(result.to_pandas().columns)
# This shows the result_key you need
```

### 3. Check system.yaml loaded correctly

```python
# In Python console
from lightspeed_evaluation.core.models.system import SystemConfig

config = SystemConfig.from_yaml("config/system.yaml")
print(config.default_turn_metrics_metadata.keys())
# Should see "ragas:your_metric"
```

### 4. Test with single evaluation

```bash
# Create minimal test yaml
cat > test_metric.yaml << EOF
- conversation_group_id: TEST
  turns:
    - turn_id: turn1
      query: "test query"
      response: "test response"
      contexts: ["test context"]
      expected_response: "test"
      turn_metrics:
        - ragas:your_metric
EOF

# Run it
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data test_metric.yaml \
    --output-dir test_output/
```

---

## Common Issues

### Issue: "Unsupported Ragas metric: your_metric"

**Cause:** Not registered in `supported_metrics` dict

**Fix:** Add to `self.supported_metrics` in `__init__`

---

### Issue: "KeyError: 'result_key'"

**Cause:** Wrong `result_key` in `_evaluate_metric` call

**Fix:** Check ragas output DataFrame columns (see debugging tip #2)

---

### Issue: "Metric requires 'ground_truth' but not provided"

**Cause:** Metric needs `expected_response` but you didn't pass it

**Fix:** Add to dataset_dict:
```python
dataset_dict = {
    # ...
    "ground_truth": [turn_data.expected_response],
}
```

---

### Issue: Metric always returns ERROR

**Cause:** Ragas library not installed or LLM not configured

**Fix:**
```bash
# Check ragas installed
python -c "from ragas.metrics import YourMetricClass"

# Check LLM config
grep "llm:" config/system.yaml -A 10
```

---

## Full Example: Adding noise_sensitivity

Here's a complete example assuming ragas has a `NoiseSensitivity` metric:

**1. system.yaml:**
```yaml
metrics_metadata:
  turn_level:
    "ragas:noise_sensitivity":
      threshold: 0.7
      description: "Robustness to noisy contexts"
      default: false
```

**2. ragas.py imports:**
```python
from ragas.metrics import (
    # ... existing ...
    NoiseSensitivity,
)
```

**3. ragas.py registration:**
```python
self.supported_metrics = {
    # ... existing ...
    "noise_sensitivity": self._evaluate_noise_sensitivity,
}
```

**4. ragas.py implementation:**
```python
def _evaluate_noise_sensitivity(
    self,
    _conv_data: Any,
    _turn_idx: Optional[int],
    turn_data: Optional[TurnData],
    is_conversation: bool,
) -> tuple[Optional[float], str]:
    """Evaluate noise sensitivity."""
    if is_conversation:
        return None, "Noise sensitivity is a turn-level metric"

    query, response, contexts = self._extract_turn_data(turn_data)

    dataset_dict = {
        "question": [query],
        "answer": [response],
        "contexts": [contexts],
    }

    return self._evaluate_metric(
        NoiseSensitivity,
        {},
        dataset_dict,
        "noise_sensitivity",  # Assuming ragas returns this column name
        "noise sensitivity",
    )
```

**5. test.yaml:**
```yaml
turns:
  - query: "How to install DHCP in RHEL 10?"
    turn_metrics:
      - ragas:noise_sensitivity
```

**Done!** The metric will now run and output results.

---

## Summary Checklist

When adding a new ragas metric:

- [ ] Add to `config/system.yaml` under `metrics_metadata.turn_level`
- [ ] Import ragas class in `src/lightspeed_evaluation/core/metrics/ragas.py`
- [ ] Register in `self.supported_metrics` dict
- [ ] Implement `_evaluate_YOUR_METRIC` method
- [ ] Check ragas docs for required dataset_dict fields
- [ ] Find correct result_key from ragas output
- [ ] Test with minimal YAML file
- [ ] Add to actual test configurations

**Time required:** 15-30 minutes per metric (once you understand the flow)

---

**Questions?** See existing metrics in `ragas.py` as examples or ask for help!
