"""Linux Expert Agent - RHEL expertise for JIRA ticket analysis.

Forms hypotheses about correct answers and synthesizes verified responses
using facts retrieved by Solr Expert Agent.

Uses Claude Agent SDK with Vertex AI.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import query as claude_query, ClaudeAgentOptions
from pydantic import BaseModel

from .solr_expert import (
    SolrExpertAgent,
    VerificationQuery,
    VerificationResult,
)

logger = logging.getLogger(__name__)


class TicketQueryExtraction(BaseModel):
    """Final extracted query with verified response."""

    ticket_key: str
    query: str
    expected_response: str
    confidence: str  # HIGH|MEDIUM|LOW
    reasoning: str
    sources: list[str]  # Source URLs from Solr
    inferred: bool  # Was this inferred (vs extracted from ticket)


@dataclass
class LinuxExpertAgent:
    """Linux Expert Agent - forms hypotheses and synthesizes verified answers.

    15+ years RHEL expertise, uses Solr Expert for fact verification.
    Uses Claude Agent SDK with Vertex AI for authentication.
    """

    model: str = "claude-sonnet-4-5@20250929"

    async def extract_with_verification(
        self,
        ticket: dict[str, Any],
        solr_expert: SolrExpertAgent,
    ) -> TicketQueryExtraction:
        """Extract query and expected response with Solr verification.

        Workflow:
            1. Form hypothesis about correct answer
            2. Generate verification queries
            3. Solr Expert searches documentation
            4. Synthesize verified answer

        Args:
            ticket: JIRA ticket dict
            solr_expert: Solr Expert Agent for verification

        Returns:
            TicketQueryExtraction with verified answer
        """
        key = ticket.get("key", "UNKNOWN")
        fields = ticket.get("fields", {})
        summary = fields.get("summary", "") or ""
        description = self._extract_description(fields.get("description", ""))

        logger.info(f"\n{'='*80}")
        logger.info(f"Processing: {key}")
        logger.info(f"Summary: {summary}")
        logger.info(f"{'='*80}")

        # Step 1: Form hypothesis and generate verification queries
        hypothesis_result = await self._form_hypothesis(key, summary, description)

        logger.info("\n[Linux Expert] Hypothesis formed:")
        logger.info(f"  Query: {hypothesis_result['query']}")
        logger.info(f"  Hypothesis: {hypothesis_result['hypothesis'][:200]}...")
        logger.info(
            f"  Verification queries: {len(hypothesis_result['verification_queries'])}"
        )

        # Step 2: Solr Expert verifies facts
        verification_queries = [
            VerificationQuery(**vq) for vq in hypothesis_result["verification_queries"]
        ]

        logger.info("\n[Solr Expert] Searching for verification...")
        verification = await solr_expert.search_for_verification(verification_queries)

        logger.info(f"  Found: {len(verification.found_docs)} documents")
        logger.info(f"  Confidence: {verification.confidence}")
        logger.info(f"  Sources: {len(verification.source_urls)} URLs")

        # Step 3: Synthesize verified answer
        logger.info("\n[Linux Expert] Synthesizing verified answer...")
        final_answer = await self._synthesize_verified_answer(
            key,
            summary,
            description,
            hypothesis_result,
            verification,
        )

        logger.info(f"  Final confidence: {final_answer['confidence']}")
        logger.info(f"  Inferred: {final_answer['inferred']}")

        return TicketQueryExtraction(
            ticket_key=key,
            query=final_answer["query"],
            expected_response=final_answer["expected_response"],
            confidence=final_answer["confidence"],
            reasoning=final_answer["reasoning"],
            sources=final_answer["sources"],
            inferred=final_answer["inferred"],
        )

    async def _form_hypothesis(
        self,
        key: str,
        summary: str,
        description: str,
    ) -> dict[str, Any]:
        """Form hypothesis about correct answer and generate verification queries.

        Args:
            key: JIRA ticket key
            summary: Ticket summary
            description: Ticket description

        Returns:
            Dict with query, hypothesis, verification_queries
        """
        system_prompt = """You are a Senior Red Hat Enterprise Linux (RHEL) Support Engineer with 15+ years experience.

Your expertise covers:
- RHEL versions 6 through 10 (lifecycle, features, EOL dates)
- System administration (systemd, networking, storage, security)
- Container technologies (Podman, RHEL container compatibility)
- Package management (DNF, RPM, application streams)
- Red Hat support policies and lifecycle management

You are analyzing a JIRA ticket about an incorrect CLA answer. Your task:

1. **Extract the user query** - reformulate if vague
2. **Form hypothesis** about the correct answer based on your RHEL expertise
3. **Generate 2-5 verification queries** to search RHEL documentation

Return JSON:
{
  "query": "precise technical question",
  "hypothesis": "your initial answer based on expertise",
  "verification_queries": [
    {
      "query": "RHEL 6 EOL date",
      "context": "Need to verify when RHEL 6 reached end of life",
      "expected_doc_type": "documentation"
    }
  ]
}
"""

        # Combine system prompt + user task into single prompt
        full_prompt = f"""{system_prompt}

---

Analyze this JIRA ticket:

Ticket: {key}
Summary: {summary}
Description: {description}

Extract the user query, form your hypothesis about the correct answer, and generate verification queries to check facts in RHEL documentation.

Return your response as JSON only."""

        # Temporarily unset GOOGLE_APPLICATION_CREDENTIALS for Claude SDK
        saved_google_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

        try:
            # Use Claude Agent SDK - iterate async generator
            options = ClaudeAgentOptions(
                model=self.model,
                max_turns=1,
            )

            response_text = ""
            async for message in claude_query(prompt=full_prompt, options=options):
                # Extract text from AssistantMessage content blocks
                if hasattr(message, "content"):
                    for block in message.content:
                        if hasattr(block, "text"):
                            response_text += block.text

            # Parse JSON from response
            json_match = re.search(
                r"```json\s*(\{.+?\})\s*```", response_text, re.DOTALL
            )
            if json_match:
                response_text = json_match.group(1)

            return json.loads(response_text)

        finally:
            # Restore GOOGLE_APPLICATION_CREDENTIALS for Gemini
            if saved_google_creds:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved_google_creds

    async def _synthesize_verified_answer(
        self,
        key: str,
        summary: str,
        description: str,
        hypothesis: dict[str, Any],
        verification: VerificationResult,
    ) -> dict[str, Any]:
        """Synthesize verified answer from Solr search results.

        Args:
            key: JIRA ticket key
            summary: Ticket summary
            description: Ticket description
            hypothesis: Initial hypothesis from _form_hypothesis
            verification: Verification results from Solr Expert

        Returns:
            Dict with query, expected_response, confidence, reasoning, sources, inferred
        """
        system_prompt = """You are a Senior Red Hat Enterprise Linux (RHEL) Support Engineer.

You previously formed a hypothesis about the correct answer. Now you have verification from actual RHEL documentation.

Your task: Synthesize a verified answer using:
1. Your RHEL expertise
2. Facts from retrieved documentation
3. Exact quotes where applicable

Return JSON:
{
  "query": "final refined query",
  "expected_response": "verified answer with sources OR 'TODO: <reason>'",
  "confidence": "HIGH|MEDIUM|LOW",
  "reasoning": "why this confidence level",
  "sources": ["url1", "url2"],
  "inferred": true/false
}

Confidence levels:
- HIGH: Multiple docs confirm facts, official lifecycle/support policy
- MEDIUM: Some docs found but version-specific details uncertain
- LOW: Insufficient docs, conflicting info, mark as TODO
"""

        # Build context from verification
        # Use first 2000 chars to ensure tables and detailed content are included
        doc_context = "\n\n".join(
            [
                f"**{doc['title']}**\n{doc['url']}\n{doc['content'][:2000]}..."
                for doc in verification.found_docs[:5]
            ]
        )

        user_prompt = f"""Original ticket:
Ticket: {key}
Summary: {summary}

Your hypothesis:
Query: {hypothesis['query']}
Hypothesis: {hypothesis['hypothesis']}

Verification results from RHEL documentation:
{doc_context}

Key facts found:
{chr(10).join(f'- {fact}' for fact in verification.key_facts)}

Solr confidence: {verification.confidence}

Synthesize the final verified answer.

Return your response as JSON only."""

        # Combine system prompt + user task into single prompt
        full_prompt = f"""{system_prompt}

---

{user_prompt}"""

        # Temporarily unset GOOGLE_APPLICATION_CREDENTIALS for Claude SDK
        saved_google_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

        try:
            # Use Claude Agent SDK - iterate async generator
            options = ClaudeAgentOptions(
                model=self.model,
                max_turns=1,
            )

            response_text = ""
            async for message in claude_query(prompt=full_prompt, options=options):
                # Extract text from AssistantMessage content blocks
                if hasattr(message, "content"):
                    for block in message.content:
                        if hasattr(block, "text"):
                            response_text += block.text

            # Parse JSON
            json_match = re.search(
                r"```json\s*(\{.+?\})\s*```", response_text, re.DOTALL
            )
            if json_match:
                response_text = json_match.group(1)

            return json.loads(response_text)

        finally:
            # Restore GOOGLE_APPLICATION_CREDENTIALS for Gemini
            if saved_google_creds:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved_google_creds

    def _extract_description(self, description: Any) -> str:
        """Extract plain text from Atlassian Document Format (ADF).

        Args:
            description: Ticket description (may be ADF dict or plain string)

        Returns:
            Plain text description
        """
        if isinstance(description, dict):
            # ADF format - extract text from content blocks
            text_parts = []

            def extract_text(node):
                if isinstance(node, dict):
                    if node.get("type") == "text":
                        text_parts.append(node.get("text", ""))
                    if "content" in node:
                        for child in node["content"]:
                            extract_text(child)
                elif isinstance(node, list):
                    for item in node:
                        extract_text(item)

            extract_text(description)
            return " ".join(text_parts)

        return str(description) if description else ""
