# Performance Metrics Design

Design for adding performance and scale testing metrics to lightspeed-evaluation framework.

## Problem Statement

LightSpeed Evaluation currently focuses on answer quality metrics (correctness, faithfulness, relevance) but lacks performance metrics required for release qualification:

- **No inference latency tracking** - Time from question submission to first/final token
- **No throughput measurement** - Questions/second, tokens/second
- **No resource monitoring** - Memory, CPU, concurrent request handling
- **No performance regression detection** - No baseline comparison for perf tests

This prevents automated perf/scale testing required for release gates.

## Requirements

### Release Testing Criteria

Performance metrics must support these release qualification tests:

1. **Latency benchmarks**:
   - P50, P95, P99 response times < defined thresholds
   - Time-to-first-token (TTFT) < 2 seconds for streaming
   - End-to-end latency < 30 seconds for complex queries

2. **Throughput benchmarks**:
   - Sustain N questions/second under load
   - Tokens/second generation rate
   - Concurrent request capacity

3. **Resource limits**:
   - Memory usage stays below ceiling
   - CPU utilization stays below ceiling
   - No memory leaks over extended runs

4. **Regression detection**:
   - Performance within 10% of baseline
   - No degradation across releases

### Integration Requirements

- Minimal changes to existing evaluation configs
- Work with current metrics (Ragas, DeepEval, custom)
- Support both streaming and non-streaming APIs
- Export data compatible with existing reports
- Thread-safe for concurrent evaluations

## Proposed Architecture

### 1. Performance Metrics as Custom Metrics

Add new custom metrics to `src/lightspeed_evaluation/core/metrics/custom/performance/`:

```
custom/
└── performance/
    ├── __init__.py
    ├── latency_metric.py      # Response time measurement
    ├── throughput_metric.py   # Requests/tokens per second
    ├── resource_metric.py     # Memory/CPU monitoring
    └── baseline_metric.py     # Regression detection
```

### 2. API Client Instrumentation

Modify `src/lightspeed_evaluation/core/api/client.py` to capture timing:

```python
from dataclasses import dataclass
from time import perf_counter
from typing import Optional

@dataclass
class PerformanceMetrics:
    """Performance data captured during API call."""
    
    # Latency
    time_to_first_token: Optional[float] = None  # Seconds (streaming only)
    time_to_last_token: float = 0.0              # Total response time
    
    # Throughput
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_per_second: float = 0.0
    
    # Resource (sampled during call)
    peak_memory_mb: float = 0.0
    avg_cpu_percent: float = 0.0
    
    # Metadata
    timestamp: float = 0.0
    model: str = ""
    streaming: bool = False


class APIClient:
    def query(self, question: str, streaming: bool = False) -> tuple[str, PerformanceMetrics]:
        """Execute query and return (response, performance_metrics)."""
        
        start_time = perf_counter()
        perf = PerformanceMetrics(
            timestamp=start_time,
            model=self.model,
            streaming=streaming,
        )
        
        # Resource monitoring
        monitor = ResourceMonitor()
        monitor.start()
        
        if streaming:
            # Track TTFT
            first_token_time = None
            response_chunks = []
            
            for chunk in self._stream_response(question):
                if first_token_time is None:
                    first_token_time = perf_counter()
                    perf.time_to_first_token = first_token_time - start_time
                
                response_chunks.append(chunk)
            
            response = "".join(response_chunks)
        else:
            # Non-streaming
            response = self._get_response(question)
        
        # Finalize metrics
        end_time = perf_counter()
        perf.time_to_last_token = end_time - start_time
        
        # Get token counts from API response metadata
        perf.total_tokens = self._last_response_tokens
        perf.completion_tokens = self._last_completion_tokens
        perf.prompt_tokens = self._last_prompt_tokens
        
        if perf.time_to_last_token > 0:
            perf.tokens_per_second = perf.completion_tokens / perf.time_to_last_token
        
        # Stop resource monitoring
        perf.peak_memory_mb, perf.avg_cpu_percent = monitor.stop()
        
        return response, perf
```

### 3. Resource Monitor

```python
import psutil
import threading
from time import sleep, perf_counter
from typing import Tuple

class ResourceMonitor:
    """Monitor CPU and memory during operations."""
    
    def __init__(self, sample_interval: float = 0.1):
        self.sample_interval = sample_interval
        self._thread = None
        self._stop_event = threading.Event()
        self._samples = []
        self._process = psutil.Process()
    
    def start(self):
        """Start monitoring in background thread."""
        self._stop_event.clear()
        self._samples = []
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> Tuple[float, float]:
        """Stop monitoring and return (peak_memory_mb, avg_cpu_percent)."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        
        if not self._samples:
            return 0.0, 0.0
        
        memory_samples = [s[0] for s in self._samples]
        cpu_samples = [s[1] for s in self._samples]
        
        peak_memory_mb = max(memory_samples)
        avg_cpu_percent = sum(cpu_samples) / len(cpu_samples)
        
        return peak_memory_mb, avg_cpu_percent
    
    def _monitor_loop(self):
        """Background monitoring loop."""
        while not self._stop_event.is_set():
            try:
                mem_mb = self._process.memory_info().rss / 1024 / 1024
                cpu_pct = self._process.cpu_percent(interval=None)
                self._samples.append((mem_mb, cpu_pct))
            except Exception:
                pass  # Process might have ended
            
            sleep(self.sample_interval)
```

### 4. Latency Metric

```python
from dataclasses import dataclass
from typing import Dict, Any, List
from lightspeed_evaluation.core.metrics.custom.base import CustomMetric

@dataclass
class LatencyMetric(CustomMetric):
    """Measure API response latency (TTFT, total time)."""
    
    name: str = "latency"
    
    # Thresholds (seconds)
    ttft_threshold: float = 2.0      # Time to first token
    total_threshold: float = 30.0    # Total response time
    
    def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        performance_metrics: "PerformanceMetrics",  # From API client
        **kwargs
    ) -> Dict[str, Any]:
        """Evaluate latency performance."""
        
        ttft = performance_metrics.time_to_first_token
        total = performance_metrics.time_to_last_token
        
        # Pass/fail based on thresholds
        ttft_pass = ttft is None or ttft <= self.ttft_threshold
        total_pass = total <= self.total_threshold
        
        return {
            "time_to_first_token_ms": ttft * 1000 if ttft else None,
            "time_to_last_token_ms": total * 1000,
            "ttft_threshold_ms": self.ttft_threshold * 1000,
            "total_threshold_ms": self.total_threshold * 1000,
            "ttft_pass": ttft_pass,
            "total_pass": total_pass,
            "latency_pass": ttft_pass and total_pass,
        }
```

### 5. Throughput Metric

```python
from dataclasses import dataclass
from typing import Dict, Any, List
from lightspeed_evaluation.core.metrics.custom.base import CustomMetric

@dataclass
class ThroughputMetric(CustomMetric):
    """Measure tokens/second generation rate."""
    
    name: str = "throughput"
    
    # Thresholds
    min_tokens_per_second: float = 10.0  # Minimum acceptable rate
    
    def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        performance_metrics: "PerformanceMetrics",
        **kwargs
    ) -> Dict[str, Any]:
        """Evaluate throughput performance."""
        
        tps = performance_metrics.tokens_per_second
        total_tokens = performance_metrics.total_tokens
        
        return {
            "tokens_per_second": tps,
            "total_tokens": total_tokens,
            "prompt_tokens": performance_metrics.prompt_tokens,
            "completion_tokens": performance_metrics.completion_tokens,
            "throughput_pass": tps >= self.min_tokens_per_second,
            "min_threshold": self.min_tokens_per_second,
        }
```

### 6. Resource Metric

```python
from dataclasses import dataclass
from typing import Dict, Any, List
from lightspeed_evaluation.core.metrics.custom.base import CustomMetric

@dataclass
class ResourceMetric(CustomMetric):
    """Monitor memory and CPU usage."""
    
    name: str = "resource_usage"
    
    # Thresholds
    max_memory_mb: float = 2048.0   # 2GB
    max_cpu_percent: float = 80.0   # 80% CPU
    
    def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        performance_metrics: "PerformanceMetrics",
        **kwargs
    ) -> Dict[str, Any]:
        """Evaluate resource usage."""
        
        memory = performance_metrics.peak_memory_mb
        cpu = performance_metrics.avg_cpu_percent
        
        return {
            "peak_memory_mb": memory,
            "avg_cpu_percent": cpu,
            "max_memory_threshold_mb": self.max_memory_mb,
            "max_cpu_threshold_percent": self.max_cpu_percent,
            "memory_pass": memory <= self.max_memory_mb,
            "cpu_pass": cpu <= self.max_cpu_percent,
            "resource_pass": memory <= self.max_memory_mb and cpu <= self.max_cpu_percent,
        }
```

### 7. Baseline Comparison Metric

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
from lightspeed_evaluation.core.metrics.custom.base import CustomMetric

@dataclass
class BaselineMetric(CustomMetric):
    """Compare performance against baseline (regression detection)."""
    
    name: str = "baseline_comparison"
    
    baseline_file: Optional[Path] = None     # Path to baseline metrics JSON
    regression_threshold: float = 0.10       # 10% degradation allowed
    
    def __post_init__(self):
        """Load baseline if provided."""
        self.baseline = None
        if self.baseline_file and self.baseline_file.exists():
            with open(self.baseline_file) as f:
                self.baseline = json.load(f)
    
    def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        performance_metrics: "PerformanceMetrics",
        **kwargs
    ) -> Dict[str, Any]:
        """Compare current performance to baseline."""
        
        if not self.baseline:
            return {
                "baseline_available": False,
                "regression_detected": False,
                "message": "No baseline available for comparison",
            }
        
        current_latency = performance_metrics.time_to_last_token
        current_tps = performance_metrics.tokens_per_second
        
        baseline_latency = self.baseline.get("p50_latency_ms", 0) / 1000
        baseline_tps = self.baseline.get("avg_tokens_per_second", 0)
        
        # Check for regressions (higher latency or lower throughput)
        latency_regression = (
            current_latency > baseline_latency * (1 + self.regression_threshold)
        )
        
        throughput_regression = (
            current_tps < baseline_tps * (1 - self.regression_threshold)
        )
        
        regression = latency_regression or throughput_regression
        
        return {
            "baseline_available": True,
            "current_latency_ms": current_latency * 1000,
            "baseline_latency_ms": baseline_latency * 1000,
            "latency_change_percent": (
                ((current_latency - baseline_latency) / baseline_latency * 100)
                if baseline_latency > 0 else 0
            ),
            "current_tokens_per_second": current_tps,
            "baseline_tokens_per_second": baseline_tps,
            "throughput_change_percent": (
                ((current_tps - baseline_tps) / baseline_tps * 100)
                if baseline_tps > 0 else 0
            ),
            "latency_regression": latency_regression,
            "throughput_regression": throughput_regression,
            "regression_detected": regression,
            "regression_threshold_percent": self.regression_threshold * 100,
        }
```

## Configuration

### Enable Performance Metrics

Add to `config/system.yaml`:

```yaml
metrics_metadata:
  # Existing quality metrics
  answer_correctness:
    framework: ragas
    # ... existing config ...
  
  # New performance metrics
  latency:
    framework: custom
    module: lightspeed_evaluation.core.metrics.custom.performance.latency_metric
    class: LatencyMetric
    config:
      ttft_threshold: 2.0      # seconds
      total_threshold: 30.0    # seconds
  
  throughput:
    framework: custom
    module: lightspeed_evaluation.core.metrics.custom.performance.throughput_metric
    class: ThroughputMetric
    config:
      min_tokens_per_second: 10.0
  
  resource_usage:
    framework: custom
    module: lightspeed_evaluation.core.metrics.custom.performance.resource_metric
    class: ResourceMetric
    config:
      max_memory_mb: 2048.0
      max_cpu_percent: 80.0
  
  baseline_comparison:
    framework: custom
    module: lightspeed_evaluation.core.metrics.custom.performance.baseline_metric
    class: BaselineMetric
    config:
      baseline_file: "baselines/performance_baseline.json"
      regression_threshold: 0.10  # 10%
```

### Use in Evaluation Config

Add to evaluation YAML (e.g., `config/patterns/AUTHENTICATION_SECURITY.yaml`):

```yaml
metadata:
  pattern_id: "AUTHENTICATION_SECURITY"
  # ... existing metadata ...

tickets:
  - jira_id: "RHELAI-1234"
    question: "How do I configure SELinux for container authentication?"
    expected_response: "..."
    metrics:
      # Quality metrics
      - answer_correctness
      - faithfulness
      - context_relevance
      
      # Performance metrics (optional, for perf testing)
      - latency
      - throughput
      - resource_usage
      - baseline_comparison
```

## Usage Patterns

### 1. Standard Quality-Only Evaluation (Default)

Existing evaluations continue to work unchanged. Performance metrics are opt-in.

```yaml
metrics:
  - answer_correctness
  - faithfulness
```

### 2. Quality + Performance Evaluation

Add performance metrics for release testing:

```yaml
metrics:
  - answer_correctness
  - faithfulness
  - latency
  - throughput
```

### 3. Performance-Only Load Testing

Create dedicated perf test configs:

```yaml
# config/perf_tests/load_test.yaml
metadata:
  test_type: "load_test"
  description: "100 concurrent requests, latency/throughput validation"

tickets:
  - jira_id: "PERF_TEST_1"
    question: "Standard query for load testing"
    expected_response: ""  # Empty = skip quality metrics
    metrics:
      - latency
      - throughput
      - resource_usage
    
  # Repeat 100x for concurrent load
  # ...
```

Run with concurrency:

```bash
uv run python -m lightspeed_evaluation.runner \
    --config config/perf_tests/load_test.yaml \
    --runs 5 \
    --concurrent 20  # New flag for concurrent execution
```

### 4. Baseline Establishment

Run once to establish baseline:

```bash
# Run performance evaluation
uv run python -m lightspeed_evaluation.runner \
    --config config/perf_tests/baseline.yaml \
    --runs 10

# Extract baseline from results
uv run python scripts/extract_performance_baseline.py \
    okp_mcp_full_output/suite_latest/run_*/evaluation_*_summary.json \
    --output baselines/performance_baseline.json
```

Baseline file format:

```json
{
  "created_at": "2026-04-15T10:30:00Z",
  "model": "claude-sonnet-4-6",
  "runs": 10,
  "p50_latency_ms": 2500.0,
  "p95_latency_ms": 4800.0,
  "p99_latency_ms": 6200.0,
  "avg_tokens_per_second": 45.2,
  "avg_memory_mb": 512.0,
  "avg_cpu_percent": 35.0
}
```

### 5. Regression Detection in CI

```bash
# CI pipeline
uv run python -m lightspeed_evaluation.runner \
    --config config/perf_tests/regression.yaml \
    --runs 5

# Check for regressions
if grep -q '"regression_detected": true' okp_mcp_full_output/suite_latest/run_*/evaluation_*_summary.json; then
    echo "❌ Performance regression detected!"
    exit 1
fi
```

## Output Format

Performance metrics integrate into existing summary JSON:

```json
{
  "jira_id": "RHELAI-1234",
  "question": "How do I configure SELinux...",
  "answer": "To configure SELinux...",
  
  "metrics": {
    "answer_correctness": 0.92,
    "faithfulness": 0.88,
    
    "latency": {
      "time_to_first_token_ms": 850.5,
      "time_to_last_token_ms": 2450.2,
      "ttft_threshold_ms": 2000.0,
      "total_threshold_ms": 30000.0,
      "ttft_pass": true,
      "total_pass": true,
      "latency_pass": true
    },
    
    "throughput": {
      "tokens_per_second": 42.3,
      "total_tokens": 1245,
      "prompt_tokens": 850,
      "completion_tokens": 395,
      "throughput_pass": true,
      "min_threshold": 10.0
    },
    
    "resource_usage": {
      "peak_memory_mb": 485.2,
      "avg_cpu_percent": 32.5,
      "max_memory_threshold_mb": 2048.0,
      "max_cpu_threshold_percent": 80.0,
      "memory_pass": true,
      "cpu_pass": true,
      "resource_pass": true
    },
    
    "baseline_comparison": {
      "baseline_available": true,
      "current_latency_ms": 2450.2,
      "baseline_latency_ms": 2500.0,
      "latency_change_percent": -2.0,
      "current_tokens_per_second": 42.3,
      "baseline_tokens_per_second": 45.2,
      "throughput_change_percent": -6.4,
      "latency_regression": false,
      "throughput_regression": false,
      "regression_detected": false,
      "regression_threshold_percent": 10.0
    }
  }
}
```

## Integration with HEAL

HEAL pattern fix workflow can use performance metrics for optimization:

```python
# In okp_mcp_agent.py diagnose_full()
def diagnose_full(
    self,
    pattern_id: str,
    runs: int = 5,
    include_performance: bool = False,  # New flag
) -> DiagnosisResult:
    """Run full evaluation with optional performance metrics."""
    
    config_path = self._prepare_config(
        pattern_id,
        include_performance=include_performance,
    )
    
    # ... run evaluation ...
    
    if include_performance:
        # Check for performance regressions
        if results.metrics.get("baseline_comparison", {}).get("regression_detected"):
            print("⚠️  Performance regression detected!")
            print(f"   Latency: {results.metrics['baseline_comparison']['latency_change_percent']:.1f}%")
            print(f"   Throughput: {results.metrics['baseline_comparison']['throughput_change_percent']:.1f}%")
```

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1)

1. Add `PerformanceMetrics` dataclass to API client
2. Instrument API client with timing capture
3. Create `ResourceMonitor` utility
4. Update `CustomMetric` base class to accept performance_metrics

**Testing:** Unit tests for timing accuracy, resource monitoring

### Phase 2: Basic Metrics (Week 1-2)

1. Implement `LatencyMetric`
2. Implement `ThroughputMetric`
3. Implement `ResourceMetric`
4. Register in `MetricManager`
5. Add to `config/system.yaml`

**Testing:** Integration tests with mocked API calls

### Phase 3: Baseline & Reporting (Week 2-3)

1. Implement `BaselineMetric`
2. Create `extract_performance_baseline.py` script
3. Update output handlers to include performance data
4. Add performance visualization to reports

**Testing:** End-to-end tests with real API calls

### Phase 4: Concurrency & Load Testing (Week 3-4)

1. Add `--concurrent` flag to runner
2. Implement concurrent request handling with thread pool
3. Create load test example configs
4. Document load testing patterns

**Testing:** Load tests with varying concurrency levels

### Phase 5: HEAL Integration (Week 4-5)

1. Add performance tracking to pattern fix workflow
2. Create performance regression detection in batch runs
3. Add performance metrics to review reports
4. Document usage in HEAL workflows

**Testing:** Full pattern fix workflow with performance metrics

## Security Considerations

- **Resource monitoring**: Only monitor own process (no system-wide access needed)
- **Baseline files**: Validate JSON schema before loading
- **Concurrency**: Use thread-safe queue for concurrent metrics collection
- **No external dependencies**: Use stdlib (`threading`, `psutil` already in deps)

## Performance Impact

- **Timing overhead**: < 1ms (using `perf_counter()`)
- **Resource monitoring**: ~0.1% CPU (sampling every 100ms in background thread)
- **Memory overhead**: ~10KB per evaluation (metrics storage)
- **No impact on quality metrics**: Performance tracking is independent

## Success Criteria

1. **Release qualification**: Can run perf/scale tests to validate release candidates
2. **Regression detection**: Detect >10% performance degradation automatically
3. **Zero quality impact**: No changes to existing quality metric behavior
4. **Minimal config changes**: Performance metrics opt-in via YAML
5. **Production ready**: Passes pre-commit checks, >80% test coverage
