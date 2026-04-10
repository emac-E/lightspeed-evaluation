# Multi-Agent JIRA Ticket Extraction with Solr Verification

## Architecture: Linux Expert + Solr Expert Collaboration

### Problem with Single-Agent Approach

**Linux Expert alone:**
- ✅ Domain knowledge and reasoning
- ✅ Can infer based on patterns
- ❌ Training data may be outdated (cutoff date)
- ❌ Cannot verify facts against current docs
- ❌ Risk of hallucinating incorrect details

**Solr Expert alone:**
- ✅ Access to actual RHEL documentation
- ✅ Always up-to-date (current index)
- ❌ No reasoning about what to search for
- ❌ Cannot interpret relevance to ticket
- ❌ Just returns docs, doesn't synthesize answer

**Solution: Multi-Agent Collaboration**

```
┌─────────────────────────────────────────────────────────────┐
│                    JIRA Ticket Input                        │
│  "Incorrect answer: Can I run RHEL 6 container on RHEL 9?" │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────┐
         │   Linux Expert Agent    │
         │  (Domain Reasoning)     │
         └─────────────┬───────────┘
                       │
                       │ Forms hypothesis:
                       │ "RHEL 6 is EOL, likely unsupported
                       │  on RHEL 9. Need to verify."
                       │
                       ▼
         ┌─────────────────────────┐
         │   Solr Expert Agent     │
         │  (Fact Verification)    │
         └─────────────┬───────────┘
                       │
                       │ Searches Solr for:
                       │ - "RHEL 6 EOL date"
                       │ - "Container compatibility matrix"
                       │ - "RHEL 6 RHEL 9 container support"
                       │
                       ▼
         ┌─────────────────────────┐
         │   Returns Documents     │
         │ + Relevance Scores      │
         └─────────────┬───────────┘
                       │
                       │ Found docs:
                       │ 1. "RHEL 6 Lifecycle" (EOL: Nov 2020)
                       │ 2. "Container Compatibility Matrix"
                       │ 3. "RHEL 9 Release Notes"
                       │
                       ▼
         ┌─────────────────────────┐
         │   Linux Expert Agent    │
         │  (Synthesis)            │
         └─────────────┬───────────┘
                       │
                       │ Combines:
                       │ - Domain knowledge
                       │ - Verified facts from Solr
                       │ - Actual doc snippets
                       │
                       ▼
         ┌─────────────────────────┐
         │  Verified Expected      │
         │  Answer + Confidence    │
         └─────────────────────────┘
```

## Implementation

### 1. Solr Expert Agent

```python
class SolrExpertAgent:
    """Agent specialized in querying Solr for RHEL documentation.
    
    Has direct access to the same Solr instance being tested by CLA.
    Uses okp-mcp tools to search and retrieve documentation.
    """
    
    def __init__(self, solr_url: str = "http://127.0.0.1:8983"):
        self.solr_url = solr_url
        # Initialize MCP connection to okp-mcp
        self.mcp_client = initialize_okp_mcp_client()
    
    async def search_for_verification(
        self,
        search_queries: List[str],
        context: str
    ) -> Dict[str, Any]:
        """Search Solr to verify facts related to a ticket.
        
        Args:
            search_queries: List of search terms to try
            context: Context about what we're verifying
            
        Returns:
            {
                'found_docs': [...],
                'key_facts': [...],
                'confidence': 'high|medium|low',
                'source_urls': [...]
            }
        """
        results = {
            'found_docs': [],
            'key_facts': [],
            'confidence': 'low',
            'source_urls': []
        }
        
        # Use okp-mcp search_portal tool
        for query in search_queries:
            response = await self.mcp_client.call_tool(
                "search_portal",
                query=query,
                max_results=5
            )
            
            if response['chunks']:
                results['found_docs'].extend(response['chunks'])
                results['source_urls'].extend([
                    chunk['url'] for chunk in response['chunks']
                ])
        
        # Extract key facts using Claude
        if results['found_docs']:
            facts_prompt = f"""From these RHEL documentation snippets, extract key facts 
relevant to: {context}

Documentation snippets:
{json.dumps(results['found_docs'], indent=2)}

Extract:
1. Definitive facts (EOL dates, version numbers, support status)
2. Direct quotes that answer the question
3. URLs to official documentation

Return as JSON.
"""
            
            # Call Claude to extract facts
            facts_response = await self._extract_facts(facts_prompt)
            results['key_facts'] = facts_response['facts']
            results['confidence'] = facts_response['confidence']
        
        return results
    
    async def verify_hypothesis(
        self,
        hypothesis: str,
        search_strategy: List[str]
    ) -> Dict[str, Any]:
        """Verify a Linux Expert's hypothesis using Solr docs.
        
        Args:
            hypothesis: What the Linux Expert believes
            search_strategy: How to search for verification
            
        Returns:
            {
                'verified': bool,
                'confidence': str,
                'supporting_evidence': [...],
                'conflicting_evidence': [...]
            }
        """
        # Search Solr with multiple strategies
        all_docs = []
        for search_term in search_strategy:
            docs = await self.search_for_verification([search_term], hypothesis)
            all_docs.extend(docs['found_docs'])
        
        # Analyze if docs support or contradict hypothesis
        verification_prompt = f"""Hypothesis to verify:
{hypothesis}

Documentation found in Solr:
{json.dumps(all_docs, indent=2)}

Does the documentation support, contradict, or remain silent on this hypothesis?

Return JSON:
{{
    "verified": true/false,
    "confidence": "high|medium|low",
    "supporting_evidence": ["quote 1", "quote 2"],
    "conflicting_evidence": ["quote 1"],
    "urls": ["url1", "url2"]
}}
"""
        
        return await self._analyze_verification(verification_prompt)


class LinuxExpertAgent:
    """Agent with RHEL expertise that uses Solr verification.
    
    Collaborates with SolrExpertAgent to verify facts.
    """
    
    def __init__(self, solr_expert: SolrExpertAgent):
        self.solr_expert = solr_expert
        self.system_prompt = LINUX_EXPERT_SYSTEM_PROMPT
    
    async def extract_with_verification(
        self,
        ticket: Dict[str, Any]
    ) -> TicketQuery:
        """Extract query and expected response with Solr verification.
        
        Workflow:
        1. Analyze ticket and form hypothesis
        2. Identify what needs verification
        3. Ask Solr Expert to verify facts
        4. Synthesize verified answer
        """
        
        # Step 1: Initial analysis
        initial_analysis = await self._analyze_ticket(ticket)
        # Returns:
        # {
        #   'query': "Can I run RHEL 6 container on RHEL 9?",
        #   'hypothesis': "RHEL 6 is EOL, unsupported on RHEL 9",
        #   'needs_verification': [
        #       'RHEL 6 EOL date',
        #       'Container compatibility matrix',
        #       'RHEL 9 container support policy'
        #   ],
        #   'confidence_without_verification': 'low'
        # }
        
        # Step 2: Get Solr Expert to verify
        verification_results = await self.solr_expert.search_for_verification(
            search_queries=initial_analysis['needs_verification'],
            context=initial_analysis['hypothesis']
        )
        
        # Step 3: Synthesize verified answer
        synthesis_prompt = f"""Original ticket analysis:
{json.dumps(initial_analysis, indent=2)}

Verified facts from RHEL documentation (Solr):
{json.dumps(verification_results, indent=2)}

Now provide the final expected response:
1. Use ONLY verified facts from Solr docs
2. Include direct quotes where appropriate
3. Reference the actual URLs found
4. Mark confidence as HIGH if facts verified, MEDIUM if partial, LOW if unverified

Return JSON:
{{
    "query": "precise technical question",
    "expected_response": "verified answer based on Solr docs",
    "confidence": "high|medium|low",
    "reasoning": "explain what was verified vs inferred",
    "source_urls": ["url1", "url2"],
    "verified_facts": ["fact1", "fact2"],
    "unverified_claims": ["claim1"]
}}
"""
        
        final_answer = await self._synthesize_answer(synthesis_prompt)
        
        return TicketQuery(
            ticket_key=ticket['key'],
            query=final_answer['query'],
            expected_response=final_answer['expected_response'],
            confidence=final_answer['confidence'],
            reasoning=final_answer['reasoning'],
            source_urls=final_answer['source_urls']
        )
```

### 2. Collaborative Workflow Example

**Ticket: RSPEED-2482**
```
Summary: Incorrect answer: Can I run RHEL 6 container on RHEL 9?
Description: User asked about RHEL 6 support. CLA said supported. Wrong.
```

**Step 1: Linux Expert Initial Analysis**

```python
analysis = {
    'query': 'Can I run a RHEL 6 container on RHEL 9?',
    'hypothesis': '''
        RHEL 6 containers on RHEL 9 are likely UNSUPPORTED because:
        1. RHEL 6 reached End of Life (EOL) around 2020
        2. RHEL 9 was released in 2022
        3. Red Hat typically doesn't support EOL versions on new hosts
        4. Container compatibility matrix should document this
    ''',
    'needs_verification': [
        'RHEL 6 end of life date',
        'RHEL 9 container compatibility matrix',
        'Container support policy for EOL versions',
        'RHEL 6 RHEL 9 container support status'
    ],
    'confidence_without_verification': 'medium'  # Reasonable hypothesis but needs facts
}
```

**Step 2: Solr Expert Verification**

```python
# Solr Expert searches using okp-mcp
solr_results = await solr_expert.search_for_verification(
    search_queries=[
        "RHEL 6 end of life EOL date",
        "container compatibility matrix RHEL",
        "RHEL 6 container RHEL 9 support"
    ],
    context="Verifying RHEL 6 container support on RHEL 9"
)

# Solr Expert returns:
{
    'found_docs': [
        {
            'url': 'access.redhat.com/support/policy/updates/errata',
            'title': 'Red Hat Enterprise Linux Life Cycle',
            'snippet': '''
                RHEL 6 Maintenance Support 2 Phase ended November 30, 2020.
                Extended Life-cycle Support available until June 30, 2024.
            ''',
            'relevance_score': 0.95
        },
        {
            'url': 'access.redhat.com/articles/rhel-container-compatibility',
            'title': 'Red Hat Enterprise Linux Container Compatibility Matrix',
            'snippet': '''
                RHEL 6-based container images are not supported on RHEL 9 hosts.
                Supported combinations listed in the compatibility matrix...
            ''',
            'relevance_score': 0.98
        },
        {
            'url': 'access.redhat.com/support/policy/rhel-app-streams-life-cycle',
            'title': 'Application Streams Life Cycle',
            'snippet': '''
                Container images follow RHEL lifecycle policy. EOL versions
                are not supported for new host operating systems.
            ''',
            'relevance_score': 0.87
        }
    ],
    'key_facts': [
        'RHEL 6 Maintenance Support ended November 30, 2020',
        'RHEL 6 container images are not supported on RHEL 9 hosts',
        'Container support follows RHEL lifecycle policy'
    ],
    'confidence': 'high',  # Multiple authoritative sources confirm
    'source_urls': [
        'access.redhat.com/support/policy/updates/errata',
        'access.redhat.com/articles/rhel-container-compatibility',
        'access.redhat.com/support/policy/rhel-app-streams-life-cycle'
    ]
}
```

**Step 3: Linux Expert Synthesis**

```python
final_answer = {
    'ticket_key': 'RSPEED-2482',
    'query': 'Can I run a RHEL 6 container on RHEL 9 host?',
    'expected_response': '''
RHEL 6 containers are UNSUPPORTED on RHEL 9 hosts per the Red Hat Container 
Compatibility Matrix.

Key facts:
- RHEL 6 Maintenance Support ended November 30, 2020
- RHEL 6-based container images are not supported on RHEL 9 hosts
- Container support follows RHEL lifecycle policy (EOL versions not supported 
  on newer host OS versions)

For supported container configurations, refer to:
- Red Hat Enterprise Linux Container Compatibility Matrix
- RHEL Application Streams Life Cycle policy

Recommendation: Upgrade containerized applications to RHEL 8 or RHEL 9 base images.
    ''',
    'confidence': 'high',  # ✅ Verified against actual RHEL docs in Solr
    'reasoning': '''
Hypothesis: "RHEL 6 unsupported on RHEL 9" - VERIFIED by Solr docs

Verified facts:
✓ RHEL 6 EOL date (Nov 30, 2020) - from lifecycle policy doc
✓ Explicit statement: "RHEL 6 containers not supported on RHEL 9" - from compatibility matrix
✓ Policy: EOL versions not supported on new hosts - from app streams lifecycle doc

All key claims verified against authoritative Red Hat documentation.
Confidence upgraded from MEDIUM → HIGH due to Solr verification.
    ''',
    'source_urls': [
        'access.redhat.com/support/policy/updates/errata',
        'access.redhat.com/articles/rhel-container-compatibility',
        'access.redhat.com/support/policy/rhel-app-streams-life-cycle'
    ],
    'verified_facts': [
        'RHEL 6 EOL: November 30, 2020',
        'RHEL 6 containers unsupported on RHEL 9 (per compatibility matrix)',
        'Container support follows RHEL lifecycle policy'
    ],
    'unverified_claims': []  # Everything verified!
}
```

## Integration with okp-mcp

### Using Existing MCP Tools

The Solr Expert agent can use the same MCP tools that CLA uses:

```python
async def initialize_okp_mcp_client():
    """Initialize connection to okp-mcp running on localhost:8001."""
    from claude_agent_sdk import query, ClaudeAgentOptions
    
    # okp-mcp is already running for CLA testing
    # Connect to it via MCP protocol
    
    options = ClaudeAgentOptions(
        model="claude-sonnet-4-5",
        allowed_tools=[
            "mcp__okp-mcp__search_portal",      # Main search
            "mcp__okp-mcp__get_document",       # Full doc retrieval
            "mcp__okp-mcp__search_solutions",   # KCS articles
            "mcp__okp-mcp__search_cves",        # CVE lookup
        ],
        permission_mode="auto"
    )
    
    return options


# Solr Expert uses these tools
async def solr_expert_search(query: str):
    """Search using okp-mcp tools."""
    
    prompt = f"""Use the search_portal tool to find RHEL documentation about:
    {query}
    
    Return the top 5 most relevant results with snippets.
    """
    
    results = []
    async for message in query(prompt=prompt, options=mcp_options):
        if hasattr(message, 'result'):
            results.append(message.result)
    
    return results
```

### Benefits of Using okp-mcp

1. **Same index as CLA** - Verifying against the exact same data CLA uses
2. **Same search logic** - Using the same portal.py intent detection and boosts
3. **Real-time** - Always current with latest Solr index
4. **No duplication** - Reusing existing infrastructure
5. **Consistency** - Expected answers match what CLA can actually retrieve

## Enhanced Confidence Levels

With Solr verification, confidence becomes more objective:

```python
def calculate_confidence(verification_results: Dict) -> str:
    """Calculate confidence based on Solr verification.
    
    HIGH: Multiple authoritative sources confirm all key facts
    MEDIUM: Some facts verified, others inferred
    LOW: Minimal or no verification from Solr
    """
    
    verified_count = len(verification_results['verified_facts'])
    unverified_count = len(verification_results['unverified_claims'])
    doc_count = len(verification_results['found_docs'])
    avg_relevance = np.mean([d['score'] for d in verification_results['found_docs']])
    
    if verified_count >= 3 and unverified_count == 0 and avg_relevance > 0.8:
        return "high"  # Strong verification
    elif verified_count >= 1 and avg_relevance > 0.6:
        return "medium"  # Partial verification
    else:
        return "low"  # Weak or no verification
```

## Output Format Enhancement

```yaml
conversation_group_id: RSPEED_2482
metadata:
  jira_ticket: RSPEED-2482
  jira_url: https://redhat.atlassian.net/browse/RSPEED-2482
  extraction_method: multi_agent_verified
  linux_expert_confidence: medium (before verification)
  solr_verification_confidence: high
  final_confidence: high ⬆️ (upgraded after verification)
  source_urls:
    - access.redhat.com/support/policy/updates/errata
    - access.redhat.com/articles/rhel-container-compatibility
  verified_facts:
    - RHEL 6 EOL: November 30, 2020
    - RHEL 6 containers unsupported on RHEL 9
turns:
  - query: "Can I run a RHEL 6 container on RHEL 9 host?"
    expected_response: |
      ✅ SOLR-VERIFIED ANSWER
      
      RHEL 6 containers are UNSUPPORTED on RHEL 9 hosts per the Red Hat 
      Container Compatibility Matrix.
      
      Key facts (verified from Solr docs):
      - RHEL 6 Maintenance Support ended November 30, 2020
      - RHEL 6-based container images are not supported on RHEL 9 hosts
      - Container support follows RHEL lifecycle policy
      
      Sources:
      - Red Hat Enterprise Linux Container Compatibility Matrix
      - RHEL Application Streams Life Cycle policy
      
      Recommendation: Upgrade to RHEL 8 or RHEL 9 base images.
    expected_urls: []  # Will be discovered during bootstrap
    turn_metrics: [...]
```

## Fallback Strategy

If Solr verification fails (e.g., Solr down, no docs found):

```python
if solr_verification_failed:
    # Fall back to Linux Expert only
    result = await linux_expert.extract_without_verification(ticket)
    result.confidence = "medium-unverified"
    result.expected_response = f"""
⚠️  UNVERIFIED (Solr search failed)

{result.expected_response}

NOTE: This answer was inferred from domain knowledge but could not be 
verified against RHEL documentation due to Solr unavailability.
SME review strongly recommended.
    """
```

## Expected Impact

### Quantitative Improvements

**Current (single agent, no Solr):**
- Extraction rate: 21% (explicit in tickets)
- High confidence inferred: ~35% (estimated)
- Total ready: ~56%
- SME workload: ~44 tickets

**With Multi-Agent + Solr Verification:**
- Extraction rate: 21% (explicit)
- **High confidence verified: ~60%** (Solr-backed)
- Medium confidence: ~15% (partial verification)
- Total ready: **~96%**
- SME workload: ~4 tickets (just the LOW confidence ones)

**Confidence boost:**
- Before Solr: "I think RHEL 6 is EOL" → MEDIUM confidence
- After Solr: "Solr docs confirm RHEL 6 EOL Nov 30, 2020" → HIGH confidence

### Qualitative Improvements

1. **Factual accuracy** - Grounded in actual RHEL docs, not training data
2. **URL references** - Can include actual doc URLs in expected response
3. **Exact quotes** - Can use exact wording from official documentation
4. **Verifiable claims** - Every fact traceable to source doc
5. **Reduced hallucination** - Cross-referenced against real index

## Implementation Plan

### Phase 1: Proof of Concept (1 week)
- Implement SolrExpertAgent with okp-mcp integration
- Test on 10 tickets manually
- Measure verification success rate
- Compare with single-agent approach

**Success criteria:**
- Solr finds relevant docs for >80% of queries
- Confidence upgrades from MEDIUM→HIGH in >50% of cases
- Zero hallucinations (all facts verified)

### Phase 2: Full Integration (2 weeks)
- Integrate into fetch_jira_tickets_direct.py
- Add multi-agent mode flag (--use-multi-agent)
- Implement fallback when Solr unavailable
- Add comprehensive logging of agent collaboration

### Phase 3: Validation (2 weeks)
- Run on all 131 CLA bug tickets
- SME validates 25% of high-confidence verified answers
- Compare accuracy: multi-agent vs single-agent
- Measure extraction rate improvement

**Success criteria:**
- Extraction rate >90% (vs current 21%)
- SME validation accuracy >95%
- High confidence answers require minimal SME review

## Recommendation

**✅ STRONGLY RECOMMEND implementing multi-agent approach**

The combination of:
- Linux Expert's domain reasoning
- Solr Expert's factual verification
- Access to the actual documentation being tested

...creates a powerful system that is both intelligent AND grounded in truth.

**Key advantages over single-agent:**
1. Facts verified against actual docs (not training data)
2. Confidence levels become objective (based on retrieval success)
3. Can reference exact URLs and quotes
4. Dramatically reduces hallucination risk
5. SME workload reduced by ~90% (vs current 100%)

**Risk mitigation:**
- Fallback to single-agent if Solr unavailable
- Still mark all inferred content clearly
- SME spot-check recommended even for HIGH confidence

This approach leverages the best of both worlds: human-like reasoning + machine-verifiable facts.
