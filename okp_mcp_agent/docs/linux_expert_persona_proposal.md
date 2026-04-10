# Linux Expert Persona for JIRA Ticket → YAML Automation

## Current Problem

**Extraction Rate: 21%**
- Out of 100 CLA incorrect-answer tickets fetched
- Only 21 had extractable expected responses
- 79 marked as "TODO: Expected response not specified - requires SME input"

**Why so low?**
- Tickets often lack explicit "expected answer" sections
- Descriptions use technical shorthand or assume domain knowledge
- Some tickets just say "wrong answer" without stating correct answer
- Tickets written by engineers, not test writers

## Proposed Solution: Linux/RHEL Expert Persona

Give the extraction agent a system-level persona with deep RHEL expertise to:
1. **Infer** technically correct expected answers even when not explicitly stated
2. **Reformulate** vague queries into precise technical questions
3. **Apply** RHEL lifecycle, support policy, and documentation knowledge
4. **Flag** uncertainty when domain knowledge insufficient

## Example Improvements

### Before (Simple Extraction)

**Ticket RSPEED-2482:**
```
Summary: Incorrect answer: Can I run a RHEL 6 container on RHEL 9?
Description: User asked about RHEL 6 container support. CLA said it's supported. This is wrong.
```

**Simple extraction result:**
```yaml
query: "Can I run a RHEL 6 container on RHEL 9?"
expected_response: "TODO: Expected response not specified in ticket - requires SME input"
reasoning: "No explicit expected answer in ticket description"
```

### After (Linux Expert Persona)

**Expert extraction result:**
```yaml
query: "Can I run a RHEL 6 container on RHEL 9?"
expected_response: |
  RHEL 6 containers on RHEL 9 hosts are UNSUPPORTED per the Red Hat Container
  Compatibility Matrix. RHEL 6 reached End of Life (EOL) in November 2020 and
  is not supported for containerization on RHEL 9 hosts (released May 2022).
  
  For supported container configurations, refer to:
  - Red Hat Container Compatibility Matrix
  - RHEL Application Streams Lifecycle documentation
  
  Recommended: Upgrade containerized applications to RHEL 8 or RHEL 9 base images.

reasoning: |
  Inferred from RHEL lifecycle policy and container compatibility requirements.
  RHEL 6 EOL date (Nov 2020) predates RHEL 9 release (May 2022).
  Container compatibility matrix does not list RHEL 6 as supported on RHEL 9.
  
  Confidence: HIGH (based on documented EOL policy)
  Source: Agent domain knowledge (RHEL lifecycle + container support policy)
  
  ⚠️  EXPERT-INFERRED - Recommend SME validation before production use
```

### Example 2: Query Reformulation

**Ticket RSPEED-2113:**
```
Summary: Incorrect answer: Steps for creating the bond with nmcli
Description: Wrong steps given. Check the bonding guide.
```

**Before (simple):**
```yaml
query: "Steps for creating the bond with nmcli"
expected_response: "TODO: Expected response not specified"
```

**After (expert):**
```yaml
query: "How do I create a network bond (bonding interface) using nmcli in RHEL 9?"
expected_response: |
  To create a bonding interface with nmcli:
  
  1. Create the bond connection:
     nmcli connection add type bond con-name bond0 ifname bond0 mode active-backup
  
  2. Add slave interfaces:
     nmcli connection add type ethernet slave-type bond con-name bond0-port1 \
       ifname eth0 master bond0
     nmcli connection add type ethernet slave-type bond con-name bond0-port2 \
       ifname eth1 master bond0
  
  3. Bring up the bond:
     nmcli connection up bond0
  
  Common modes: active-backup, balance-rr, 802.3ad (LACP)
  
  Refer to RHEL networking guide for detailed bonding configuration.

reasoning: |
  Inferred correct procedure from RHEL 9 networking documentation structure.
  nmcli is the standard tool for network configuration (NetworkManager).
  Common pattern: create bond → add slaves → activate.
  
  Confidence: MEDIUM (specific flags may vary by RHEL version)
  Source: Agent knowledge of nmcli bonding workflow
  
  ⚠️  EXPERT-INFERRED - SME should verify exact syntax for RHEL 9
```

## Implementation Design

### Enhanced System Prompt

```python
LINUX_EXPERT_SYSTEM_PROMPT = """You are a Senior Red Hat Enterprise Linux (RHEL) 
Support Engineer and Technical Expert with 15+ years of experience.

Your expertise covers:
- RHEL versions 6 through 10 (lifecycle, features, EOL dates)
- System administration (systemd, networking, storage, security)
- Container technologies (Podman, RHEL container compatibility)
- Package management (DNF, RPM, application streams)
- Red Hat support policies and lifecycle management
- Common troubleshooting patterns and customer issues

When analyzing JIRA tickets about incorrect CLA answers:

1. UNDERSTAND the technical issue deeply
   - What RHEL component is involved?
   - What version specifics matter?
   - What are the lifecycle/support implications?

2. INFER the correct answer using your expertise
   - Apply Red Hat support policies
   - Consider version-specific behavior
   - Reference official documentation patterns
   - Identify if feature is supported/deprecated/EOL

3. FORMULATE clear, technically accurate expected responses
   - State facts clearly (supported/unsupported/deprecated)
   - Include relevant version numbers
   - Reference official docs (by topic, not exact URLs)
   - Provide brief reasoning

4. MARK your confidence level
   - HIGH: Based on well-documented RHEL policy (EOL dates, support matrix)
   - MEDIUM: Based on common patterns but version-specific details may vary
   - LOW: Uncertain, insufficient information, mark as TODO

5. ALWAYS distinguish between:
   - Facts extracted from ticket (explicitly stated)
   - Facts inferred from expertise (your knowledge)
   - Mark inferred answers with ⚠️ EXPERT-INFERRED

Your goal: Maximize automation while maintaining accuracy. When uncertain, prefer
marking as TODO over guessing. But when you have strong domain knowledge (EOL dates,
support policies, standard procedures), use it confidently.
"""
```

### Confidence Levels

```python
class ConfidenceLevel:
    HIGH = "high"      # Use inferred answer (>85% confidence)
    MEDIUM = "medium"  # Flag for SME review but provide answer (60-85%)
    LOW = "low"        # Mark as TODO, insufficient to infer (<60%)

def should_use_inferred_answer(confidence: str, validation_mode: str) -> bool:
    """Decide whether to use agent-inferred answer.
    
    Args:
        confidence: Agent's confidence level
        validation_mode: "strict" or "permissive"
    
    Returns:
        True if should use inferred answer
    """
    if validation_mode == "strict":
        return confidence == ConfidenceLevel.HIGH
    else:  # permissive
        return confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]
```

### Modified Extraction Function

```python
async def extract_query_with_expert_inference(
    ticket: dict[str, Any],
    model: str = "claude-sonnet-4-5",
    use_expert_persona: bool = True,
    confidence_threshold: str = "medium",
) -> TicketQuery:
    """Extract query and infer expected response using Linux expert persona.
    
    Args:
        ticket: JIRA ticket dictionary
        model: Claude model to use
        use_expert_persona: Enable expert inference (vs simple extraction)
        confidence_threshold: "high" (strict) or "medium" (permissive)
    
    Returns:
        TicketQuery with query, expected_response, confidence, reasoning
    """
    
    key = ticket.get("key", "UNKNOWN")
    fields = ticket.get("fields", {})
    summary = fields.get("summary", "")
    description = fields.get("description", "")
    
    # Build prompt with or without expert persona
    if use_expert_persona:
        system_prompt = LINUX_EXPERT_SYSTEM_PROMPT
        task_prompt = f"""Analyze this JIRA ticket about an incorrect CLA answer:

Ticket: {key}
Summary: {summary}
Description: {description}

Extract or infer:
1. USER QUERY: The question the user asked
   - Reformulate if vague
   - Make technically precise
   
2. EXPECTED RESPONSE: The correct answer
   - Extract if explicitly stated in ticket
   - OR infer using your RHEL expertise if not stated
   - Include version-specific details
   - Reference relevant documentation topics
   
3. CONFIDENCE LEVEL: How certain are you?
   - "high": Based on documented RHEL policy/EOL/support matrix
   - "medium": Based on common patterns, may need version verification
   - "low": Insufficient information to infer
   
4. REASONING: Explain your answer
   - What facts did you extract vs infer?
   - What domain knowledge did you apply?
   - What should SME verify?

Return JSON:
{{
  "ticket_key": "{key}",
  "query": "precise technical question",
  "expected_response": "correct answer OR 'TODO: <reason>'",
  "confidence": "high|medium|low",
  "reasoning": "explanation of extraction/inference",
  "inferred": true/false
}}

If confidence is "low", set expected_response to "TODO: Insufficient information to infer correct answer"
"""
    else:
        # Simple extraction (current approach)
        system_prompt = "Extract information from JIRA tickets."
        task_prompt = f"""Extract the user query and expected response from this ticket.
        
Ticket: {key}
Summary: {summary}
Description: {description}

If expected response not explicitly stated, use: "TODO: Expected response not specified in ticket"
"""
    
    # Call Claude with appropriate prompt
    # ... (rest of implementation)
```

## Validation Strategy

### Three-Tier Validation

**Tier 1: Automatic (High Confidence)**
- Agent confidence = "high"
- Based on documented facts (EOL dates, support matrix)
- Directly usable in test configs
- Example: "RHEL 6 is EOL" (fact-based)

**Tier 2: SME Review (Medium Confidence)**  
- Agent confidence = "medium"
- Technically sound but version-specific details uncertain
- Add to `jira_open_tickets_REVIEW.yaml` for SME spot-check
- Example: Specific nmcli command syntax

**Tier 3: Manual (Low Confidence)**
- Agent confidence = "low"
- Mark as TODO, requires full SME input
- Add to `tickets_SME_needed.yaml`
- Example: Obscure edge cases, conflicting information

### Output File Structure

```bash
config/
├── jira_open_tickets.yaml           # High confidence (auto-extracted + high-confidence inferred)
├── jira_open_tickets_REVIEW.yaml    # Medium confidence (SME spot-check recommended)
└── tickets_SME_needed.yaml          # Low confidence (full SME input required)
```

## Safeguards Against Hallucination

### 1. Confidence Thresholds
```python
# Only use inferred answers when confidence is justified
if confidence == "low" or not has_supporting_facts():
    return "TODO: Insufficient information"
```

### 2. Fact-Based Grounding
```python
# Anchor inference to verifiable facts
VERIFIABLE_FACTS = {
    "rhel_6_eol": "2020-11-30",
    "rhel_7_eol": "2024-06-30",
    "rhel_8_eol": "2029-05-31",
    # ... etc
}

# Use these in reasoning
if "RHEL 6" in query and current_date > VERIFIABLE_FACTS["rhel_6_eol"]:
    confidence = "high"  # Fact-based
```

### 3. Explicit Uncertainty Markers
```yaml
expected_response: |
  ⚠️  EXPERT-INFERRED (not explicitly stated in ticket)
  
  RHEL 6 containers are UNSUPPORTED on RHEL 9...
  
  SME should verify: Exact wording in Container Compatibility Matrix
```

### 4. Version-Specific Caveats
```python
# Flag when version matters
if version_mentioned and version != "latest":
    add_caveat(f"⚠️ Answer specific to {version} - verify if still current")
```

## Gradual Rollout Plan

### Phase 1: Experiment (2 weeks)
- Run expert persona on 20 tickets
- Compare with simple extraction
- SME validates all inferred answers
- Measure accuracy and time savings

**Success metrics:**
- Inferred answer accuracy >90%
- Extraction rate improvement (21% → >50%)
- SME review time reduced

### Phase 2: Controlled Deployment (1 month)
- Use expert persona for new tickets
- Confidence threshold = "high" (strict mode)
- SME spot-checks 25% of inferred answers
- Monitor for hallucinations

**Success metrics:**
- Hallucination rate <5%
- SME validates accuracy >95%
- Productivity gain measured

### Phase 3: Production (ongoing)
- Expert persona default for all tickets
- Confidence threshold = "medium" (permissive)
- SME reviews REVIEW.yaml only
- Continuous monitoring

## Expected Impact

### Quantitative Improvements

**Current state (100 tickets):**
- Extracted: 21 (21%)
- TODO: 79 (79%)
- SME workload: 79 tickets × 15 min = 19.75 hours

**With expert persona (estimated):**
- Auto-extracted: 21 (21%)
- High-confidence inferred: 35 (35%)  
- Medium-confidence inferred: 25 (25%)
- TODO (low confidence): 19 (19%)

**New SME workload:**
- Spot-check medium: 25 tickets × 5 min = 2.1 hours
- Full review low: 19 tickets × 15 min = 4.75 hours
- Total: 6.85 hours (65% reduction)

### Qualitative Improvements

**Better queries:**
- "Steps for bond with nmcli" → "How to create network bonding interface with nmcli in RHEL 9"
- More context, version-specific, precise

**Richer expected responses:**
- Include context (why something is unsupported)
- Reference doc topics (not just URLs)
- Provide alternatives when applicable

**Faster iteration:**
- Fewer SME blockers
- More tickets ready for bootstrap immediately
- Pattern learning accelerated

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Hallucinated incorrect answers | HIGH | Confidence thresholds, SME validation, fact-grounding |
| Outdated knowledge (old training data) | MEDIUM | Version-specific caveats, SME reviews, knowledge cutoff warnings |
| Over-confidence in uncertain areas | MEDIUM | Three-tier validation, explicit uncertainty markers |
| SME trust erosion if errors found | HIGH | Clear marking of inferred answers, conservative confidence |

## Recommendation

**✅ Proceed with expert persona** with these safeguards:

1. **Start conservative** - Only use HIGH confidence inferences initially
2. **Mark all inferences** - ⚠️ EXPERT-INFERRED tag required
3. **SME validation** - Spot-check 25% of inferred answers in Phase 1
4. **Monitor closely** - Track hallucination rate, adjust thresholds
5. **Iterate quickly** - Gather feedback, tune prompts, improve grounding

**Expected ROI:**
- 65% reduction in SME manual work
- 3x more tickets ready for automated bootstrap
- Faster feedback loop for fixing CLA issues
- Knowledge capture (agent reasoning → documentation)

The key is balancing automation (speed) with accuracy (trust). The three-tier confidence system and explicit uncertainty markers provide that balance.
