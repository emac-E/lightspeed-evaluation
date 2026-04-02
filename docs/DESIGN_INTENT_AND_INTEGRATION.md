# OKP-MCP Autonomous Agent - Design Intent & Integration Guide

## Overview

This document describes the **design intent** and **integration architecture** for the OKP-MCP Autonomous Agent, enabling it to be used by external autonomous systems like cron jobs, JIRA monitoring services, and other workflow automation tools.

For **technical implementation details**, see [MULTI_STAGE_TESTING_PLAN.md](MULTI_STAGE_TESTING_PLAN.md).

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL TRIGGER SYSTEMS                     │
├─────────────┬──────────────┬────────────────┬──────────────────┤
│ Cron Jobs   │ JIRA Monitor │ GitHub Actions │ Manual CLI       │
└──────┬──────┴──────┬───────┴────────┬───────┴──────┬───────────┘
       │             │                │              │
       └─────────────┴────────────────┴──────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              OKP-MCP AUTONOMOUS AGENT (CLI)                     │
│                                                                 │
│  Entry Points:                                                  │
│    - python scripts/okp_mcp_agent.py diagnose RSPEED-XXXX      │
│    - python scripts/okp_mcp_agent.py fix RSPEED-XXXX           │
│    - python scripts/okp_mcp_agent.py validate                  │
│                                                                 │
│  Outputs:                                                       │
│    - Exit codes (0 = success, 1 = failure)                     │
│    - JSON reports (--output-format json)                       │
│    - Git worktrees with proposed fixes                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EVALUATION PIPELINE                         │
│                                                                 │
│  Components:                                                    │
│    - lightspeed-evaluation framework                           │
│    - okp-mcp MCP server (localhost:8001)                       │
│    - lightspeed-stack (/v1/infer endpoint)                     │
│    - LLM Advisor (Claude via Vertex AI)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OUTPUT ARTIFACTS                             │
│                                                                 │
│  - Evaluation reports (CSV, JSON)                              │
│  - Git worktrees with code changes                             │
│  - Metrics dashboards                                          │
│  - JIRA comment updates                                        │
└─────────────────────────────────────────────────────────────────┘
```

## Integration Points

### 1. Command-Line Interface (Primary Integration Point)

The agent is designed to be called from **any external system** via its CLI:

```bash
# Diagnose a ticket (read-only, no changes)
python scripts/okp_mcp_agent.py diagnose RSPEED-2482 \
  --output-format json \
  --output-file diagnosis.json

# Fix a ticket (creates worktree with proposed changes)
python scripts/okp_mcp_agent.py fix RSPEED-2482 \
  --max-iterations 10 \
  --output-format json \
  --output-file fix_report.json

# Validate all test suites (regression check)
python scripts/okp_mcp_agent.py validate \
  --output-format json \
  --output-file validation.json
```

**Exit Codes:**
- `0` - Success (ticket fixed, no regressions)
- `1` - Failure (could not fix, regressions detected)
- `2` - Configuration error
- `3` - Authentication error

### 2. JSON Output Format (Machine-Readable)

Enable JSON output for integration with automation systems:

```bash
python scripts/okp_mcp_agent.py diagnose RSPEED-2482 --output-format json
```

**Example Output:**
```json
{
  "ticket_id": "RSPEED-2482",
  "status": "retrieval_problem",
  "metrics": {
    "url_f1": 0.33,
    "mrr": 0.20,
    "context_relevance": 0.45,
    "faithfulness": 0.60,
    "answer_correctness": 0.55
  },
  "recommendation": {
    "action": "boost_query_change",
    "file": "src/okp_mcp/portal.py",
    "change": "Increase documentKind:solution boost from 2.0 to 4.0",
    "confidence": "high"
  },
  "llm_reasoning": "The query mentions 'container' but retrieving wrong doc types...",
  "next_step": "Use fast iteration mode (retrieval-only)",
  "timestamp": "2026-04-01T14:30:00Z"
}
```

### 3. Git Worktree Output (Safe Isolation)

When using `fix` command, the agent creates an **isolated git worktree** with proposed changes:

```bash
python scripts/okp_mcp_agent.py fix RSPEED-2482 --output-worktree
```

**Output:**
```
✅ Created worktree: /tmp/okp-mcp-fix-RSPEED-2482-20260401-143000
   Branch: fix/RSPEED-2482-auto
   Changes: src/okp_mcp/portal.py (5 lines modified)
```

**Integration workflow:**
1. Agent creates worktree with fix
2. External system runs tests in worktree
3. If tests pass → merge worktree changes
4. If tests fail → delete worktree, try again

### 4. JIRA Integration (Future)

The agent can be extended to **read from and write to JIRA**:

**Read JIRA tickets:**
```bash
# Get all open RSPEED tickets with label "incorrect-answer"
python scripts/okp_mcp_agent.py jira list \
  --project RSPEED \
  --status "Open" \
  --label "incorrect-answer" \
  --output-format json
```

**Update JIRA with results:**
```bash
# Post diagnosis to JIRA as comment
python scripts/okp_mcp_agent.py diagnose RSPEED-2482 \
  --post-to-jira \
  --jira-comment-template "Auto-diagnosis: {diagnosis}\nMetrics: {metrics}\nRecommendation: {recommendation}"
```

**Example JIRA comment:**
```
🤖 Auto-Diagnosis (okp-mcp-agent)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Status: RETRIEVAL PROBLEM
Confidence: HIGH

Metrics:
• URL F1: 0.33 (threshold: 0.7) ❌
• MRR: 0.20 (threshold: 0.5) ❌
• Context Relevance: 0.45 (threshold: 0.7) ❌
• Faithfulness: 0.60 (threshold: 0.8) ❌

Recommendation:
📝 File: src/okp_mcp/portal.py
✏️  Change: Increase documentKind:solution boost from 2.0 to 4.0
🎯 Expected Improvement: URL F1 should increase to >0.7

Next Step:
Use fast iteration mode (retrieval-only) for rapid testing.

Generated: 2026-04-01 14:30:00 UTC
```

## Automation Workflows

### Workflow 1: Daily JIRA Ticket Scanning

**Use Case:** Check for new RSPEED tickets with "incorrect-answer" label every night.

**Cron Job Example:**
```bash
#!/bin/bash
# /etc/cron.d/okp-mcp-daily-scan
# Run every day at 2 AM
0 2 * * * /home/automation/okp-mcp/scripts/daily_scan.sh
```

**Script (`daily_scan.sh`):**
```bash
#!/bin/bash
set -euo pipefail

WORK_DIR="/home/automation/okp-mcp"
LOG_DIR="/var/log/okp-mcp-agent"
DATE=$(date +%Y%m%d-%H%M%S)

cd "$WORK_DIR"

# 1. Get new JIRA tickets
echo "[${DATE}] Fetching JIRA tickets..."
python scripts/okp_mcp_agent.py jira list \
  --project RSPEED \
  --status "Open" \
  --label "incorrect-answer" \
  --created-within "24h" \
  --output-format json \
  > "${LOG_DIR}/tickets_${DATE}.json"

# 2. Diagnose each ticket
jq -r '.tickets[].key' "${LOG_DIR}/tickets_${DATE}.json" | while read -r ticket_id; do
  echo "[${DATE}] Diagnosing ${ticket_id}..."

  python scripts/okp_mcp_agent.py diagnose "$ticket_id" \
    --output-format json \
    --output-file "${LOG_DIR}/diagnosis_${ticket_id}_${DATE}.json" \
    --post-to-jira \
    --jira-label "auto-diagnosed"
done

# 3. Generate summary report
python scripts/okp_mcp_agent.py report \
  --input-dir "${LOG_DIR}" \
  --output-file "${LOG_DIR}/daily_summary_${DATE}.html" \
  --email-to "team@example.com"

echo "[${DATE}] Daily scan complete."
```

**Outputs:**
- JSON diagnosis for each ticket
- JIRA comments with recommendations
- HTML email summary to team
- Tickets labeled "auto-diagnosed"

### Workflow 2: Weekly Automated Fix Attempts

**Use Case:** Attempt to fix high-priority tickets automatically, create PRs for review.

**Cron Job Example:**
```bash
#!/bin/bash
# /etc/cron.d/okp-mcp-weekly-fix
# Run every Monday at 3 AM
0 3 * * 1 /home/automation/okp-mcp/scripts/weekly_fix.sh
```

**Script (`weekly_fix.sh`):**
```bash
#!/bin/bash
set -euo pipefail

WORK_DIR="/home/automation/okp-mcp"
LOG_DIR="/var/log/okp-mcp-agent"
DATE=$(date +%Y%m%d-%H%M%S)

cd "$WORK_DIR"

# 1. Get high-priority tickets diagnosed as retrieval problems
python scripts/okp_mcp_agent.py jira list \
  --project RSPEED \
  --priority "High" \
  --label "auto-diagnosed,retrieval-problem" \
  --status "Open" \
  --output-format json \
  > "${LOG_DIR}/priority_tickets_${DATE}.json"

# 2. Attempt to fix each ticket
jq -r '.tickets[].key' "${LOG_DIR}/priority_tickets_${DATE}.json" | while read -r ticket_id; do
  echo "[${DATE}] Attempting to fix ${ticket_id}..."

  # Create worktree with proposed fix
  if python scripts/okp_mcp_agent.py fix "$ticket_id" \
      --max-iterations 10 \
      --validate-cla-tests \
      --output-worktree \
      --output-format json \
      > "${LOG_DIR}/fix_${ticket_id}_${DATE}.json"; then

    # Fix succeeded - extract worktree path
    WORKTREE=$(jq -r '.worktree_path' "${LOG_DIR}/fix_${ticket_id}_${DATE}.json")
    BRANCH=$(jq -r '.branch' "${LOG_DIR}/fix_${ticket_id}_${DATE}.json")

    # Push branch and create PR
    cd "$WORKTREE"
    git push origin "$BRANCH"

    gh pr create \
      --title "fix: Improve retrieval for ${ticket_id}" \
      --body "$(cat ${LOG_DIR}/fix_${ticket_id}_${DATE}.json | jq -r '.pr_description')" \
      --label "auto-generated,needs-review" \
      --assignee "@me"

    # Update JIRA
    python "$WORK_DIR/scripts/okp_mcp_agent.py" jira comment "$ticket_id" \
      --message "🤖 Automated fix created: [PR Link]"

    cd "$WORK_DIR"
  else
    echo "[${DATE}] Failed to fix ${ticket_id}"

    # Update JIRA with failure
    python scripts/okp_mcp_agent.py jira comment "$ticket_id" \
      --message "⚠️ Automated fix failed. Manual intervention required."
  fi
done

echo "[${DATE}] Weekly fix run complete."
```

**Outputs:**
- Git worktrees with proposed changes
- GitHub PRs for each successful fix
- JIRA comments with PR links or failure notices
- JSON reports for each fix attempt

### Workflow 3: CI/CD Integration (GitHub Actions)

**Use Case:** Run agent on every PR to validate no regressions.

**GitHub Actions Workflow (`.github/workflows/okp-mcp-validation.yml`):**
```yaml
name: OKP-MCP Validation

on:
  pull_request:
    paths:
      - 'src/okp_mcp/**'
      - 'config/**'

jobs:
  validate:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r lightspeed-evaluation/requirements.txt

      - name: Start lightspeed-stack
        run: |
          cd lightspeed-stack
          docker-compose up -d
          sleep 30  # Wait for services

      - name: Run validation
        env:
          ANTHROPIC_VERTEX_PROJECT_ID: ${{ secrets.VERTEX_PROJECT_ID }}
          GOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GCP_CREDENTIALS }}
        run: |
          cd lightspeed-evaluation
          python scripts/okp_mcp_agent.py validate \
            --output-format json \
            --output-file validation_results.json

      - name: Check for regressions
        run: |
          # Exit with error if regressions detected
          if jq -e '.regressions | length > 0' validation_results.json; then
            echo "❌ Regressions detected!"
            jq '.regressions' validation_results.json
            exit 1
          else
            echo "✅ No regressions detected"
          fi

      - name: Post results as PR comment
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const results = JSON.parse(fs.readFileSync('validation_results.json', 'utf8'));

            const comment = `## 🤖 OKP-MCP Validation Results

            **Status:** ${results.status === 'pass' ? '✅ PASSED' : '❌ FAILED'}

            ### Test Suites
            ${results.suites.map(s => `- ${s.name}: ${s.pass_rate}% (${s.passed}/${s.total})`).join('\n')}

            ${results.regressions.length > 0 ? `
            ### ⚠️ Regressions Detected
            ${results.regressions.map(r => `- ${r.ticket}: ${r.metric} dropped by ${r.delta}`).join('\n')}
            ` : ''}
            `;

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: comment
            });

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: validation-results
          path: |
            validation_results.json
            okp_mcp_full_output/
```

**Outputs:**
- PR comments with validation status
- Artifacts with full evaluation results
- CI pass/fail based on regressions

## Data Flow

```
┌─────────────────┐
│  JIRA Ticket    │
│  RSPEED-2482    │
└────────┬────────┘
         │
         │ (1) Fetch ticket details
         ▼
┌─────────────────────────────────────┐
│  okp_mcp_agent.py diagnose          │
│  • Extract query from description   │
│  • Find test case in test suite     │
└────────┬────────────────────────────┘
         │
         │ (2) Run evaluation
         ▼
┌─────────────────────────────────────┐
│  lightspeed-evaluation              │
│  • Fast mode: localhost:8001        │
│  • Full mode: /v1/infer             │
│  • Generate metrics CSV             │
└────────┬────────────────────────────┘
         │
         │ (3) Parse results
         ▼
┌─────────────────────────────────────┐
│  Parse metrics from CSV             │
│  • URL F1, MRR                      │
│  • Faithfulness, Answer Correctness │
│  • Keywords, Forbidden Claims       │
└────────┬────────────────────────────┘
         │
         │ (4) Classify problem
         ▼
┌─────────────────────────────────────┐
│  Problem Classification             │
│  • Retrieval problem?               │
│  • Answer problem?                  │
│  • Already passing?                 │
└────────┬────────────────────────────┘
         │
         │ (5) Get LLM suggestion
         ▼
┌─────────────────────────────────────┐
│  LLM Advisor (Claude via Vertex AI) │
│  • Haiku: Classify complexity       │
│  • Sonnet: Generate suggestion      │
│  • Structured JSON output           │
└────────┬────────────────────────────┘
         │
         │ (6) Output results
         ▼
┌─────────────────────────────────────┐
│  Outputs                            │
│  • JSON report                      │
│  • JIRA comment                     │
│  • Git worktree (if fix mode)       │
│  • Metrics dashboard                │
└─────────────────────────────────────┘
```

## Configuration Management

### Environment Variables

External systems must provide these environment variables:

```bash
# Required for LLM advisor
export ANTHROPIC_VERTEX_PROJECT_ID="your-gcp-project-id"
export GOOGLE_CLAUDE_CREDENTIALS="/path/to/claude-service-account.json"

# Optional (defaults shown)
export CLOUD_ML_REGION="us-east5"

# JIRA integration (future)
export JIRA_URL="https://issues.redhat.com"
export JIRA_USERNAME="automation-bot"
export JIRA_API_TOKEN="secret"

# GitHub integration (future)
export GITHUB_TOKEN="ghp_xxxx"
```

### Config Files

**`config/agent_config.yaml`** (Future):
```yaml
agent:
  # Evaluation settings
  max_iterations: 10
  validate_cla_tests: true

  # LLM settings
  llm_advisor:
    enabled: true
    use_tiered_models: true
    simple_model: "claude-haiku-4-5@20251001"
    medium_model: "claude-sonnet-4-5@20250929"
    complex_model: "claude-opus-4-5@20250929"

  # Metric thresholds
  thresholds:
    url_f1: 0.7
    mrr: 0.5
    context_relevance: 0.7
    faithfulness: 0.8
    answer_correctness: 0.75
    response_relevancy: 0.8
    keywords: 0.7
    forbidden_claims: 1.0

  # Integration settings
  jira:
    enabled: false
    post_comments: true
    add_labels: true

  github:
    enabled: false
    create_prs: true
    auto_assign: true

  # Output settings
  output:
    format: "json"  # json, text, html
    worktree_dir: "/tmp/okp-mcp-worktrees"
    log_dir: "/var/log/okp-mcp-agent"
```

## Monitoring and Observability

### Logging

The agent outputs structured logs for monitoring:

```json
{
  "timestamp": "2026-04-01T14:30:00Z",
  "level": "INFO",
  "event": "diagnosis_complete",
  "ticket_id": "RSPEED-2482",
  "status": "retrieval_problem",
  "metrics": {
    "url_f1": 0.33,
    "duration_seconds": 45
  },
  "llm_calls": {
    "classification": {"model": "claude-haiku-4-5", "tokens": 150},
    "suggestion": {"model": "claude-sonnet-4-5", "tokens": 2048}
  }
}
```

### Metrics Dashboard (Future)

Prometheus metrics for monitoring:

```
# Tickets processed
okp_mcp_agent_tickets_total{status="success"} 42
okp_mcp_agent_tickets_total{status="failure"} 3

# Diagnosis results
okp_mcp_agent_diagnosis_type{type="retrieval_problem"} 25
okp_mcp_agent_diagnosis_type{type="answer_problem"} 10
okp_mcp_agent_diagnosis_type{type="passing"} 7

# LLM costs
okp_mcp_agent_llm_cost_usd{model="haiku"} 0.05
okp_mcp_agent_llm_cost_usd{model="sonnet"} 2.10

# Evaluation duration
okp_mcp_agent_eval_duration_seconds{mode="retrieval_only"} 30
okp_mcp_agent_eval_duration_seconds{mode="full"} 180
```

### Health Checks

```bash
# Check agent is working
python scripts/okp_mcp_agent.py health-check

# Example output:
# ✅ lightspeed-evaluation: OK
# ✅ okp-mcp server (localhost:8001): OK
# ✅ lightspeed-stack (/v1/infer): OK
# ✅ LLM advisor (Vertex AI): OK
# ✅ Git repository: OK
```

## Security and Permissions

### Required Permissions

**GCP (for LLM advisor):**
- `aiplatform.endpoints.predict` (Vertex AI User role)
- Access to Anthropic Model Garden

**JIRA (for JIRA integration):**
- Read issues
- Add comments
- Add labels
- Transition issues (future)

**GitHub (for PR creation):**
- Read repository
- Create branches
- Create pull requests
- Add comments

**File System:**
- Read: `~/Work/okp-mcp/`, `~/Work/lightspeed-evaluation/`
- Write: `/tmp/okp-mcp-worktrees/`, `/var/log/okp-mcp-agent/`

### Secrets Management

**DO NOT commit secrets to git.** Use environment variables or secret management systems:

```bash
# Option 1: Environment variables (development)
export ANTHROPIC_VERTEX_PROJECT_ID="project-id"
export GOOGLE_CLAUDE_CREDENTIALS="/path/to/key.json"

# Option 2: Secret manager (production)
gcloud secrets versions access latest --secret="okp-mcp-agent-creds" > /tmp/creds.json
export GOOGLE_CLAUDE_CREDENTIALS="/tmp/creds.json"
```

## Example Integration Scripts

### Script 1: Simple Ticket Diagnosis

```bash
#!/bin/bash
# diagnose_ticket.sh
# Usage: ./diagnose_ticket.sh RSPEED-2482

TICKET_ID="$1"
OUTPUT_DIR="/var/log/okp-mcp-agent"
DATE=$(date +%Y%m%d-%H%M%S)

python scripts/okp_mcp_agent.py diagnose "$TICKET_ID" \
  --output-format json \
  --output-file "${OUTPUT_DIR}/diagnosis_${TICKET_ID}_${DATE}.json"

# Check exit code
if [ $? -eq 0 ]; then
  echo "✅ Diagnosis complete: ${OUTPUT_DIR}/diagnosis_${TICKET_ID}_${DATE}.json"
else
  echo "❌ Diagnosis failed"
  exit 1
fi
```

### Script 2: Batch Processing

```bash
#!/bin/bash
# batch_diagnose.sh
# Usage: ./batch_diagnose.sh tickets.txt

TICKETS_FILE="$1"
OUTPUT_DIR="/var/log/okp-mcp-agent"
DATE=$(date +%Y%m%d-%H%M%S)

# Read tickets from file (one per line)
while IFS= read -r ticket_id; do
  echo "Processing $ticket_id..."

  python scripts/okp_mcp_agent.py diagnose "$ticket_id" \
    --output-format json \
    --output-file "${OUTPUT_DIR}/diagnosis_${ticket_id}_${DATE}.json"

  sleep 5  # Rate limiting
done < "$TICKETS_FILE"

# Generate summary
python scripts/okp_mcp_agent.py report \
  --input-dir "$OUTPUT_DIR" \
  --output-file "${OUTPUT_DIR}/batch_summary_${DATE}.html"
```

### Script 3: Webhook Handler

```python
#!/usr/bin/env python3
"""
webhook_handler.py
Flask app to receive JIRA webhooks and trigger agent
"""
from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/jira-webhook', methods=['POST'])
def handle_jira_webhook():
    """Handle JIRA webhook for new/updated tickets."""
    data = request.json

    # Only process specific events
    if data.get('webhookEvent') != 'jira:issue_created':
        return jsonify({"status": "ignored"}), 200

    issue = data.get('issue', {})
    ticket_id = issue.get('key')
    labels = [l.get('name') for l in issue.get('fields', {}).get('labels', [])]

    # Only process tickets with "incorrect-answer" label
    if 'incorrect-answer' not in labels:
        return jsonify({"status": "ignored"}), 200

    # Trigger diagnosis
    try:
        result = subprocess.run(
            ['python', 'scripts/okp_mcp_agent.py', 'diagnose', ticket_id,
             '--output-format', 'json',
             '--post-to-jira'],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            return jsonify({"status": "success", "ticket": ticket_id}), 200
        else:
            return jsonify({"status": "error", "message": result.stderr}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## Deployment Scenarios

### Scenario 1: Local Development

```bash
# Developer runs agent manually on their laptop
cd ~/Work/lightspeed-evaluation
python scripts/okp_mcp_agent.py diagnose RSPEED-2482
```

### Scenario 2: Cron Job on Dedicated Server

```bash
# Server runs agent on schedule
# Server has: Python 3.11, lightspeed-evaluation, okp-mcp, GCP credentials
0 2 * * * /home/automation/okp-mcp/scripts/daily_scan.sh
```

### Scenario 3: Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: okp-mcp-daily-scan
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: agent
            image: quay.io/redhat/okp-mcp-agent:latest
            env:
            - name: ANTHROPIC_VERTEX_PROJECT_ID
              valueFrom:
                secretKeyRef:
                  name: vertex-ai-creds
                  key: project-id
            - name: GOOGLE_CLAUDE_CREDENTIALS
              value: /secrets/gcp/key.json
            command:
            - /bin/bash
            - -c
            - |
              cd /app
              python scripts/okp_mcp_agent.py jira list \
                --project RSPEED \
                --status "Open" \
                --label "incorrect-answer" \
                --created-within "24h" \
                --output-format json | \
              jq -r '.tickets[].key' | \
              while read ticket; do
                python scripts/okp_mcp_agent.py diagnose "$ticket" \
                  --output-format json \
                  --post-to-jira
              done
            volumeMounts:
            - name: gcp-creds
              mountPath: /secrets/gcp
              readOnly: true
          volumes:
          - name: gcp-creds
            secret:
              secretName: vertex-ai-key
          restartPolicy: OnFailure
```

## Future Enhancements

### Phase 1 (Current)
- ✅ CLI interface with JSON output
- ✅ LLM advisor integration
- ✅ Git worktree support
- ⏳ Multi-stage validation

### Phase 2 (Next 2 Weeks)
- JIRA API integration (read tickets, post comments)
- GitHub PR creation
- Email notifications
- HTML report generation

### Phase 3 (Next Month)
- Webhook support (JIRA, GitHub)
- Prometheus metrics
- Grafana dashboards
- Kubernetes deployment manifests

### Phase 4 (Future)
- Full autonomous mode (auto-merge PRs)
- Machine learning for boost query optimization
- A/B testing framework
- Cost optimization dashboard

## Summary

This design enables the OKP-MCP Autonomous Agent to be used by:

1. **Cron Jobs**: Daily/weekly ticket scanning and fixing
2. **CI/CD Pipelines**: Regression validation on PRs
3. **JIRA Webhooks**: Real-time diagnosis when tickets created
4. **Manual CLI**: Developer-driven debugging and fixes
5. **Kubernetes CronJobs**: Scalable scheduled automation

**Key Integration Points:**
- **Input**: CLI commands with ticket IDs
- **Output**: JSON reports, git worktrees, JIRA comments
- **Monitoring**: Structured logs, Prometheus metrics
- **Security**: Environment-based secrets, IAM permissions

For technical implementation details, see [MULTI_STAGE_TESTING_PLAN.md](MULTI_STAGE_TESTING_PLAN.md).
