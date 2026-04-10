# Multi-Agent JIRA Extraction Test Plan

## Objectives
1. Verify each agent component works independently
2. Test integration between agents
3. Debug Claude Agent SDK issues systematically

## Test Plan Items

### TP-001: Claude Agent SDK Basic Connectivity
**Goal:** Verify Claude Agent SDK can make simple API calls with Vertex AI credentials

**Steps:**
1. Import claude_agent_sdk
2. Create simple prompt (< 100 chars)
3. Call query() with minimal options
4. Verify we get a response back

**Expected:** AssistantMessage with text content
**Dependencies:** ANTHROPIC_VERTEX_PROJECT_ID env var

---

### TP-002: Claude Agent SDK with Long Prompts
**Goal:** Verify SDK can handle prompts > 1000 characters

**Steps:**
1. Create prompt with system instructions + user task (> 1000 chars)
2. Call query() with max_turns=1
3. Extract text from response

**Expected:** Full response text without truncation
**Dependencies:** TP-001 passes

---

### TP-003: Claude Agent SDK JSON Output
**Goal:** Verify SDK can return structured JSON

**Steps:**
1. Create prompt requesting JSON response
2. Parse JSON from response text
3. Validate JSON structure

**Expected:** Valid JSON object matching expected schema
**Dependencies:** TP-002 passes

---

### TP-004: Solr Expert - Direct Solr Connectivity
**Goal:** Verify SolrExpertAgent can query Solr directly

**Steps:**
1. Create SolrExpertAgent instance
2. Call _query_solr() with simple query
3. Verify documents returned

**Expected:** List of document dicts with title, url, content
**Dependencies:** Solr running on localhost:8983

---

### TP-005: Solr Expert - Verification Query
**Goal:** Verify search_for_verification() works end-to-end

**Steps:**
1. Create VerificationQuery for known fact (e.g., "RHEL 6 EOL date")
2. Call search_for_verification()
3. Verify VerificationResult has docs and confidence

**Expected:** VerificationResult with HIGH/MEDIUM confidence and source URLs
**Dependencies:** TP-004 passes

---

### TP-006: Linux Expert - Hypothesis Formation
**Goal:** Verify _form_hypothesis() can analyze ticket and return JSON

**Steps:**
1. Create test ticket dict
2. Call _form_hypothesis()
3. Validate returned dict has: query, hypothesis, verification_queries

**Expected:** Dict with all required fields
**Dependencies:** TP-003 passes

---

### TP-007: Linux Expert - Answer Synthesis
**Goal:** Verify _synthesize_verified_answer() creates final response

**Steps:**
1. Create mock hypothesis dict
2. Create mock VerificationResult
3. Call _synthesize_verified_answer()
4. Validate output format

**Expected:** Dict with query, expected_response, confidence, sources, inferred
**Dependencies:** TP-003 passes

---

### TP-008: Full Integration
**Goal:** Verify complete workflow: Linux Expert ↔ Solr Expert

**Steps:**
1. Create real JIRA ticket dict
2. Initialize both agents
3. Call extract_with_verification()
4. Verify complete TicketQueryExtraction returned

**Expected:** Complete extraction with verified answer and sources
**Dependencies:** TP-005, TP-006, TP-007 pass

---

## Debugging Strategy

If TP-001 fails → Check ANTHROPIC_VERTEX_PROJECT_ID, gcloud auth
If TP-002 fails → Check prompt formatting, max_tokens
If TP-003 fails → Check JSON parsing logic
If TP-004 fails → Check Solr URL, Solr running
If TP-006/TP-007 fail → Check Claude Agent SDK error details, stderr output
If TP-008 fails → Check integration logic, async/await patterns
