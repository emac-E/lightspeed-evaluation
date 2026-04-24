"""Solr Expert Agent - searches RHEL documentation for fact verification.

Queries Solr directly to verify facts against authoritative RHEL documentation.
Designed for reuse across JIRA extraction and ticket-fixing workflows.

Features:
- Direct Solr HTTP queries (bypasses okp-mcp for stability)
- Search intelligence logging (shares knowledge with fixing agent)
- Confidence-based verification results
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class VerificationQuery(BaseModel):
    """Verification query for Solr Expert."""

    query: str
    context: str  # Why we're searching for this
    expected_doc_type: str  # solution|article|documentation


class VerificationResult(BaseModel):
    """Results from Solr Expert verification."""

    found_docs: list[dict[str, Any]]
    key_facts: list[str]
    confidence: str  # HIGH|MEDIUM|LOW
    source_urls: list[str]
    reasoning: str


@dataclass
class SolrExpertAgent:
    """Solr Expert Agent - searches RHEL documentation for fact verification.

    Queries Solr directly (not via okp-mcp) to avoid dependency on
    potentially buggy search configuration under development.

    Uses same Solr instance as okp-mcp but with direct HTTP queries.

    Features:
    - Logs all searches to search intelligence database
    - Shares knowledge with okp_mcp_agent for better diagnosis
    """

    solr_url: str = "http://localhost:8983/solr/portal"
    timeout: int = 30
    search_intelligence_mgr: Optional[Any] = None  # SearchIntelligenceManager
    ticket_key: Optional[str] = None  # Current ticket being processed

    def __post_init__(self):
        """Validate Solr URL and initialize search intelligence."""
        # Allow override via environment variable
        env_url = os.getenv("SOLR_URL")
        if env_url:
            self.solr_url = env_url.rstrip("/")

        # Initialize search intelligence if not provided
        if self.search_intelligence_mgr is None:
            try:
                from .search_intelligence import (
                    SearchIntelligenceManager,
                )

                # Default location in project directory
                db_path = Path(".claude/search_intelligence")
                self.search_intelligence_mgr = SearchIntelligenceManager(db_path)
                logger.info(f"Initialized search intelligence: {db_path}")
            except Exception as e:
                logger.warning(f"Could not initialize search intelligence: {e}")
                self.search_intelligence_mgr = None

    async def search_for_verification(
        self,
        search_queries: list[VerificationQuery],
    ) -> VerificationResult:
        """Search Solr for verification of Linux Expert's hypothesis.

        Args:
            search_queries: List of verification queries to search

        Returns:
            VerificationResult with found docs, key facts, confidence
        """
        logger.info(
            f"Solr Expert: Searching for {len(search_queries)} verification queries"
        )

        all_docs = []
        all_urls = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Search for each query
            for vq in search_queries:
                logger.debug(f"  Query: {vq.query} (context: {vq.context})")
                docs = await self._query_solr(client, vq.query, num_results=10)
                all_docs.extend(docs)
                for doc in docs:
                    if "url" in doc:
                        all_urls.add(doc["url"])

                # Log search intelligence
                if self.search_intelligence_mgr and self.ticket_key:
                    self._log_search_intelligence(vq, docs)

        # Extract key facts from top documents
        key_facts = self._extract_key_facts(all_docs, search_queries)

        # Determine confidence based on retrieval success
        confidence = self._determine_confidence(all_docs, search_queries)

        reasoning = f"Found {len(all_docs)} documents across {len(search_queries)} verification queries."
        if all_docs:
            reasoning += f" Top result: {all_docs[0].get('title', 'N/A')}"

        return VerificationResult(
            found_docs=all_docs[:10],  # Return top 10
            key_facts=key_facts,
            confidence=confidence,
            source_urls=list(all_urls)[:5],  # Top 5 unique URLs
            reasoning=reasoning,
        )

    def _build_smart_params(
        self,
        query: str,
        num_results: int = 10,
    ) -> dict[str, Any]:
        """Build RHEL-aware Solr params with better defaults.

        Non-agentic improvements over basic params:
        - Better field weights (from okp-mcp base_params)
        - Phrase boosting (pf, pf2, pf3)
        - RHEL version detection and filtering
        - Topic-specific boosts (bootloader, container, lifecycle, etc.)
        - Minimum match for precision

        Args:
            query: Search query
            num_results: Number of results to return

        Returns:
            Dict of Solr params
        """
        import re

        # Start with okp-mcp's proven base params (simplified - no highlighting)
        params = {
            "q": query,
            "defType": "edismax",
            # Improved field weights (from okp-mcp)
            "qf": "title^5 main_content^3 heading_h1^3 heading_h2 portal_synopsis^3 allTitle^3 content^2 product^2",
            # Phrase boosting for multi-word queries
            "pf": "title^8 main_content^5",
            "ps": "3",
            "pf2": "title^5 main_content^3",
            "ps2": "2",
            "pf3": "title^2 main_content^1",
            "ps3": "5",
            # Minimum match for precision (at least 2 terms for 2-4 term queries, 60% for longer)
            "mm": "2<-1 5<60%",
            "rows": num_results,
            "fl": "title,resourceName,main_content,documentKind,product,documentation_version",
            "wt": "json",
        }

        # RHEL version detection and filtering
        rhel_version = self._detect_rhel_version(query)
        if rhel_version:
            # Filter to docs for this version (allows other versions to still match, but boosts exact)
            params["bq"] = f"documentation_version:*{rhel_version}*^4"
            logger.debug(f"  Detected RHEL {rhel_version}, boosting matching docs")

        # Topic-specific boosts
        query_lower = query.lower()

        # Bootloader topics (GRUB, UEFI, boot)
        if any(kw in query_lower for kw in ["grub", "bootloader", "boot", "uefi"]):
            # Boost bootloader-specific docs
            bq = params.get("bq", "")
            params["bq"] = f"{bq} documentKind:bootloader^10" if bq else "documentKind:bootloader^10"
            logger.debug("  Topic: bootloader - boosting bootloader docs")

        # Container topics
        elif any(kw in query_lower for kw in ["container", "podman", "docker"]):
            # Boost container docs
            params["qf"] += " container_compatibility^10"
            logger.debug("  Topic: container - added container field boost")

        # Lifecycle/EOL topics
        elif any(kw in query_lower for kw in ["eol", "end of life", "lifecycle", "eus", "extended update"]):
            # Boost lifecycle docs
            params["qf"] += " lifecycle_info^8"
            logger.debug("  Topic: lifecycle - added lifecycle field boost")

        # Systemd topics
        elif any(kw in query_lower for kw in ["systemd", "service", "unit file"]):
            # Boost systemd docs
            bq = params.get("bq", "")
            params["bq"] = f"{bq} documentKind:documentation^5" if bq else "documentKind:documentation^5"
            logger.debug("  Topic: systemd - boosting documentation")

        # Networking topics
        elif any(kw in query_lower for kw in ["network", "nmcli", "bond", "interface", "ip"]):
            # Boost networking docs
            bq = params.get("bq", "")
            params["bq"] = f"{bq} documentKind:documentation^5" if bq else "documentKind:documentation^5"
            logger.debug("  Topic: networking - boosting documentation")

        return params

    def _detect_rhel_version(self, query: str) -> Optional[str]:
        """Detect RHEL version from query.

        Args:
            query: Search query

        Returns:
            Version string (e.g., "9", "8", "7") or None
        """
        import re

        # Match patterns like "RHEL 9", "rhel9", "Red Hat Enterprise Linux 8"
        patterns = [
            r"rhel\s*([6-9])",
            r"red\s+hat\s+enterprise\s+linux\s+([6-9])",
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    async def _query_solr(
        self,
        client: httpx.AsyncClient,
        query: str,
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Query Solr directly for documents.

        Args:
            client: HTTP client
            query: Search query
            num_results: Number of results to return

        Returns:
            List of document dictionaries with title, url, content
        """
        # Preprocess query for better results
        params = self._build_smart_params(query, num_results)
        logger.debug(f"  Using params: qf={params.get('qf', 'N/A')[:50]}...")

        try:
            response = await client.get(
                f"{self.solr_url}/select",
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            docs = data.get("response", {}).get("docs", [])

            # Format for consistency
            formatted_docs = []
            base_url = "https://access.redhat.com"
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

            logger.debug(f"  Found {len(formatted_docs)} documents for query: {query}")
            return formatted_docs

        except httpx.HTTPError as e:
            logger.error(f"Solr query failed: {e}")
            return []

    def _extract_key_facts(
        self,
        docs: list[dict[str, Any]],
        queries: list[VerificationQuery],
    ) -> list[str]:
        """Extract key facts from top documents.

        Args:
            docs: Retrieved documents
            queries: Original verification queries

        Returns:
            List of key facts as strings
        """
        key_facts = []

        # Get first 2-3 sentences from top 3 docs as key facts
        for doc in docs[:3]:
            content = doc.get("content", "")
            # Get first few sentences
            sentences = content.split(". ")[:2]
            if sentences:
                fact = ". ".join(sentences)
                if not fact.endswith("."):
                    fact += "."
                key_facts.append(f"{fact} (Source: {doc.get('title', 'N/A')})")

        return key_facts

    def _determine_confidence(
        self,
        docs: list[dict[str, Any]],
        queries: list[VerificationQuery],
    ) -> str:
        """Determine confidence based on retrieval success.

        Args:
            docs: Retrieved documents
            queries: Original verification queries

        Returns:
            Confidence level: HIGH, MEDIUM, or LOW
        """
        if not docs:
            return "LOW"

        # Good coverage: multiple docs per query
        if len(docs) >= len(queries) * 2:
            return "HIGH"
        # Moderate coverage: at least one doc per query
        elif len(docs) >= len(queries):
            return "MEDIUM"
        else:
            return "LOW"

    def _log_search_intelligence(
        self,
        verification_query: VerificationQuery,
        found_docs: list[dict[str, Any]],
    ) -> None:
        """Log search result to intelligence database.

        Args:
            verification_query: The query that was searched
            found_docs: Documents that were retrieved
        """
        try:
            from .search_intelligence import SearchResult

            # Convert context to topic (e.g., "Need to verify RHEL 6 EOL" → "RHEL_6_EOL")
            topic = self._context_to_topic(verification_query.context)

            # Create and log search result
            result = SearchResult.from_verification(
                query=verification_query.query,
                topic=topic,
                ticket_key=self.ticket_key or "UNKNOWN",
                found_docs=found_docs,
                confidence=(
                    "HIGH"
                    if len(found_docs) >= 2
                    else "MEDIUM" if found_docs else "LOW"
                ),
            )

            self.search_intelligence_mgr.log_search(result)
            logger.debug(
                f"Logged search intelligence: {topic} → {len(found_docs)} docs"
            )

        except Exception as e:
            logger.warning(f"Failed to log search intelligence: {e}")

    def _context_to_topic(self, context: str) -> str:
        """Convert verification context to a topic identifier.

        Args:
            context: Human-readable context (e.g., "Need to verify RHEL 6 EOL date")

        Returns:
            Topic identifier (e.g., "RHEL_6_EOL")
        """
        # Simple heuristic: extract key terms and uppercase
        context_lower = context.lower()

        # Common patterns
        if "eol" in context_lower or "end of life" in context_lower:
            if "rhel 6" in context_lower or "rhel6" in context_lower:
                return "RHEL_6_EOL"
            elif "rhel 7" in context_lower or "rhel7" in context_lower:
                return "RHEL_7_EOL"
            elif "rhel 8" in context_lower or "rhel8" in context_lower:
                return "RHEL_8_EOL"
            return "RHEL_EOL"

        if "container" in context_lower and "compatibility" in context_lower:
            return "CONTAINER_COMPATIBILITY"

        if (
            "network" in context_lower
            or "bond" in context_lower
            or "nmcli" in context_lower
        ):
            return "NETWORKING"

        if "systemd" in context_lower:
            return "SYSTEMD"

        if (
            "package" in context_lower
            or "dnf" in context_lower
            or "rpm" in context_lower
        ):
            return "PACKAGE_MANAGEMENT"

        # Fallback: use first few words
        words = context.split()[:3]
        return "_".join(word.upper() for word in words if len(word) > 2)
