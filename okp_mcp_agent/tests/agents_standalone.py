"""Standalone agent implementations for testing.

These are copies of the agents from src/ but located in tests/ directory
to avoid Claude Agent SDK loading project context (CLAUDE.md, etc.) which
causes "Command failed with exit code 1" errors.

This is a workaround until the SDK context issue is resolved.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx
from claude_agent_sdk import query as claude_query, ClaudeAgentOptions

from okp_mcp_agent.core.solr_expert import (
    VerificationQuery,
    VerificationResult,
)


@dataclass
class SolrExpertStandalone:
    """Standalone Solr Expert for testing (same as src version)."""

    solr_url: str = "http://localhost:8983/solr/portal"
    timeout: int = 30

    def __post_init__(self):
        env_url = os.getenv("SOLR_URL")
        if env_url:
            self.solr_url = env_url.rstrip("/")

    async def search_for_verification(
        self,
        search_queries: list[VerificationQuery],
    ) -> VerificationResult:
        """Search Solr for verification."""
        all_docs = []
        all_urls = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for vq in search_queries:
                docs = await self._query_solr(client, vq.query, num_results=10)
                all_docs.extend(docs)
                for doc in docs:
                    if "url" in doc:
                        all_urls.add(doc["url"])

        key_facts = [
            f"{doc['content'][:100]}. (Source: {doc.get('title', 'N/A')})"
            for doc in all_docs[:3]
        ]

        confidence = (
            "HIGH"
            if len(all_docs) >= len(search_queries) * 2
            else "MEDIUM" if all_docs else "LOW"
        )

        return VerificationResult(
            found_docs=all_docs[:10],
            key_facts=key_facts,
            confidence=confidence,
            source_urls=list(all_urls)[:5],
            reasoning=f"Found {len(all_docs)} documents",
        )

    async def _query_solr(
        self,
        client: httpx.AsyncClient,
        query: str,
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Query Solr directly."""
        params = {
            "q": query,
            "defType": "edismax",
            "qf": "title^5 main_content^2 product",
            "rows": num_results,
            "fl": "title,resourceName,main_content,documentKind,product,documentation_version",
            "wt": "json",
        }

        try:
            response = await client.get(f"{self.solr_url}/select", params=params)
            response.raise_for_status()
            data = response.json()
            docs = data.get("response", {}).get("docs", [])

            # Format documents
            base_url = "https://access.redhat.com"
            formatted_docs = []
            for doc in docs:
                # Extract scalar values from lists if needed
                title = doc.get("title", "Untitled")
                if isinstance(title, list):
                    title = title[0] if title else "Untitled"

                content = doc.get("main_content", "")
                if isinstance(content, list):
                    content = content[0] if content else ""

                # Build full URL from resourceName
                resource_name = doc.get("resourceName", "")
                url = f"{base_url}{resource_name}" if resource_name else ""

                formatted_docs.append(
                    {
                        "title": title,
                        "url": url,
                        "content": content,
                        "documentKind": doc.get("documentKind", "unknown"),
                    }
                )

            return formatted_docs
        except Exception:
            return []


@dataclass
class LinuxExpertStandalone:
    """Standalone Linux Expert for testing (same as src version but in tests/)."""

    model: str = "claude-sonnet-4-5@20250929"

    async def form_hypothesis(self, key: str, summary: str, description: str) -> dict:
        """Form hypothesis about correct answer."""
        system_prompt = """You are a Senior RHEL Support Engineer with 15+ years experience.

Expertise: RHEL 6-10, systemd, networking, containers, packages.

Task: Analyze JIRA ticket, extract query, form hypothesis, generate verification queries.

Return JSON:
{
  "query": "precise question",
  "hypothesis": "your answer",
  "verification_queries": [
    {"query": "...", "context": "...", "expected_doc_type": "..."}
  ]
}"""

        full_prompt = f"""{system_prompt}

Ticket: {key}
Summary: {summary}
Description: {description}

Return JSON only."""

        # Temporarily unset GOOGLE_APPLICATION_CREDENTIALS for Claude SDK
        saved_google_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

        try:
            options = ClaudeAgentOptions(model=self.model, max_turns=1)

            response_text = ""
            async for message in claude_query(prompt=full_prompt, options=options):
                if hasattr(message, "content"):
                    for block in message.content:
                        if hasattr(block, "text"):
                            response_text += block.text

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

    async def synthesize_answer(
        self,
        key: str,
        summary: str,
        description: str,
        hypothesis: dict,
        verification: VerificationResult,
    ) -> dict:
        """Synthesize verified answer."""
        system_prompt = """You are a Senior RHEL Support Engineer.

Synthesize verified answer using your expertise + verification docs.

Return JSON:
{
  "query": "...",
  "expected_response": "... OR 'TODO: <reason>'",
  "confidence": "HIGH|MEDIUM|LOW",
  "reasoning": "...",
  "sources": ["url1"],
  "inferred": true/false
}"""

        doc_context = "\n".join(
            [
                f"{doc['title']}: {doc['content'][:200]}"
                for doc in verification.found_docs[:3]
            ]
        )

        full_prompt = f"""{system_prompt}

Ticket: {key}
Hypothesis: {hypothesis['hypothesis']}

Docs:
{doc_context}

Solr confidence: {verification.confidence}

Return JSON only."""

        # Temporarily unset GOOGLE_APPLICATION_CREDENTIALS for Claude SDK
        saved_google_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

        try:
            options = ClaudeAgentOptions(model=self.model, max_turns=1)

            response_text = ""
            async for message in claude_query(prompt=full_prompt, options=options):
                if hasattr(message, "content"):
                    for block in message.content:
                        if hasattr(block, "text"):
                            response_text += block.text

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

    async def extract_with_verification(self, ticket: dict, solr_expert):
        """Full extraction workflow."""
        from okp_mcp_agent.core.linux_expert import TicketQueryExtraction

        key = ticket["key"]
        summary = ticket["fields"]["summary"]
        description = ticket["fields"].get("description", "")

        hypothesis = await self.form_hypothesis(key, summary, description)

        queries = [VerificationQuery(**vq) for vq in hypothesis["verification_queries"]]
        verification = await solr_expert.search_for_verification(queries)

        result = await self.synthesize_answer(
            key, summary, description, hypothesis, verification
        )

        return TicketQueryExtraction(
            ticket_key=key,
            query=result["query"],
            expected_response=result["expected_response"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            sources=result["sources"],
            inferred=result["inferred"],
        )
