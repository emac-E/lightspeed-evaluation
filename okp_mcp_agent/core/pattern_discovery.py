"""Pattern Discovery Agent - Identifies common patterns across batches of JIRA tickets.

When processing multiple tickets, this agent clusters them by:
- Problem type (EOL, version mismatch, deprecated feature, unsupported config)
- Component (containers, networking, storage, packages, systemd)
- RHEL version patterns (6→9, 7→10, etc.)

Benefits:
- Process 15 similar tickets as 1 pattern (15x efficiency)
- Consistent answers for similar issues
- Easier SME review (review pattern template, not 15 variations)
- Insights into most common problem types
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TicketClassification(BaseModel):
    """Lightweight classification of a ticket for pattern matching."""

    ticket_key: str
    query: str
    problem_type: str  # EOL_UNSUPPORTED, VERSION_MISMATCH, DEPRECATED, etc.
    components: list[str]  # containers, networking, storage, etc.
    rhel_versions: list[str]  # Mentioned RHEL versions
    keywords: list[str]  # Key technical terms


class PatternGroup(BaseModel):
    """A discovered pattern across multiple tickets."""

    pattern_id: str
    description: str
    ticket_count: int
    representative_tickets: list[str]  # 2-3 clearest examples
    matched_tickets: list[str]  # All tickets in this pattern

    # Pattern characteristics
    common_problem_type: str
    common_components: list[str]
    version_pattern: str  # e.g., ">2 major versions", "6→9 or 6→10"

    # Verification queries for the pattern (apply to all tickets)
    verification_queries: list[dict[str, str]]


class PatternTemplate(BaseModel):
    """Verified response template for a pattern.

    After Solr Expert verifies the pattern's queries, this template
    can be customized for each ticket in the pattern.
    """

    pattern_id: str
    response_template: (
        str  # With placeholders: {source_version}, {target_version}, etc.
    )
    confidence: str  # HIGH|MEDIUM|LOW
    verified_facts: dict[str, Any]  # Facts that apply to all tickets in pattern
    sources: list[str]  # Source URLs from verification


@dataclass
class PatternDiscoveryAgent:
    """Analyzes batches of tickets to identify common patterns.

    Uses Claude to cluster tickets and identify reusable response templates.
    """

    model: str = "claude-sonnet-4-5@20250929"

    async def classify_tickets(
        self,
        tickets: list[dict[str, Any]],
    ) -> list[TicketClassification]:
        """Lightweight classification of tickets for pattern discovery.

        Args:
            tickets: JIRA ticket dictionaries

        Returns:
            List of ticket classifications
        """
        from tests.agents.conftest import claude_sdk_context
        from claude_agent_sdk import query as claude_query, ClaudeAgentOptions

        classifications = []

        system_prompt = """You are a RHEL Support Analyst classifying support tickets.

For each ticket, extract:
1. **problem_type**: EOL_UNSUPPORTED, VERSION_MISMATCH, DEPRECATED_FEATURE, UNSUPPORTED_CONFIG, INCORRECT_PROCEDURE, or OTHER
2. **components**: List of involved components (containers, networking, storage, systemd, packages, security, etc.)
3. **rhel_versions**: Mentioned RHEL versions (e.g., ["6", "9"])
4. **keywords**: Key technical terms (max 5)

Return JSON array with one entry per ticket."""

        # Process in batches of 10 to avoid token limits
        batch_size = 10
        for i in range(0, len(tickets), batch_size):
            batch = tickets[i : i + batch_size]

            tickets_summary = "\n\n".join(
                [
                    f"Ticket {t['key']}:\n"
                    f"Summary: {t.get('fields', {}).get('summary', '')}\n"
                    f"Description: {str(t.get('fields', {}).get('description', ''))[:200]}"
                    for t in batch
                ]
            )

            prompt = f"""Classify these {len(batch)} tickets:

{tickets_summary}

Return JSON array."""

            # Call Claude with context manager to unset GOOGLE_APPLICATION_CREDENTIALS
            with claude_sdk_context():
                options = ClaudeAgentOptions(model=self.model, max_turns=1)

                response_text = ""
                async for message in claude_query(
                    prompt=f"{system_prompt}\n\n{prompt}", options=options
                ):
                    if hasattr(message, "content"):
                        for block in message.content:
                            if hasattr(block, "text"):
                                response_text += block.text

            # Parse JSON
            json_match = re.search(
                r"```json\s*(\[.+?\])\s*```", response_text, re.DOTALL
            )
            if json_match:
                response_text = json_match.group(1)

            batch_classifications = json.loads(response_text)
            for item in batch_classifications:
                # Normalize field names (Claude might return ticket_id instead of ticket_key)
                if "ticket_id" in item and "ticket_key" not in item:
                    item["ticket_key"] = item.pop("ticket_id")

                # Ensure query field exists (use ticket summary if missing)
                if "query" not in item and "ticket_key" in item:
                    # Find original ticket to get query
                    matching_ticket = next(
                        (t for t in tickets if t["key"] == item["ticket_key"]), None
                    )
                    if matching_ticket:
                        item["query"] = matching_ticket["fields"]["summary"]

                classifications.append(TicketClassification(**item))

        logger.info(f"Classified {len(classifications)} tickets")
        return classifications

    async def _discover_patterns_batch(
        self,
        classifications: list[TicketClassification],
        batch_name: str = "batch",
        retry_count: int = 0,
        max_retries: int = 2,
    ) -> list[PatternGroup]:
        """Discover patterns for a single batch with retry logic.

        Args:
            classifications: Ticket classifications
            batch_name: Name for logging
            retry_count: Current retry attempt
            max_retries: Maximum retry attempts

        Returns:
            List of patterns or empty list on failure
        """
        from tests.agents.conftest import claude_sdk_context
        from claude_agent_sdk import query as claude_query, ClaudeAgentOptions
        import asyncio

        logger.info(
            f"  Discovering patterns for {batch_name}: {len(classifications)} tickets"
        )

        # Build summary for Claude
        summary = "\n".join(
            [
                f"{c.ticket_key}: {c.problem_type} | {', '.join(c.components)} | RHEL {', '.join(c.rhel_versions)}"
                for c in classifications
            ]
        )

        system_prompt = """You are a RHEL Support Pattern Analyst.

Analyze tickets to identify common patterns. Group tickets that share:
1. Same root cause (EOL, version incompatibility, deprecated feature)
2. Same components
3. Similar version patterns

Only create patterns with ≥3 tickets. Output JSON:
{
  "patterns": [
    {
      "pattern_id": "EOL_CONTAINER_COMPATIBILITY",
      "description": "...",
      "ticket_count": 15,
      "representative_tickets": ["RSPEED-2482", "RSPEED-2511"],
      "matched_tickets": ["RSPEED-2482", ...],
      "common_problem_type": "EOL_UNSUPPORTED",
      "common_components": ["containers"],
      "version_pattern": ">2 major versions",
      "verification_queries": [
        {"query": "RHEL {version} EOL date", "context": "...", "expected_doc_type": "documentation"}
      ]
    }
  ],
  "ungrouped_tickets": ["RSPEED-1234"]
}"""

        prompt = f"""Analyze these {len(classifications)} tickets:

{summary}

Identify patterns (≥3 tickets per pattern)."""

        # Call Claude
        full_prompt = f"{system_prompt}\n\n{prompt}"
        logger.debug(
            f"    Prompt size: {len(full_prompt)} chars, {len(full_prompt.split())} words"
        )

        try:
            with claude_sdk_context():
                options = ClaudeAgentOptions(model=self.model, max_turns=1)

                response_text = ""
                async for message in claude_query(prompt=full_prompt, options=options):
                    if hasattr(message, "content"):
                        for block in message.content:
                            if hasattr(block, "text"):
                                response_text += block.text

            logger.debug(f"    Response size: {len(response_text)} chars")

        except Exception as e:
            logger.error(f"    Claude SDK query failed: {e}")

            # Retry with exponential backoff
            if retry_count < max_retries:
                wait_time = 2**retry_count  # 1s, 2s, 4s
                logger.warning(
                    f"    Retrying in {wait_time}s (attempt {retry_count + 1}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
                return await self._discover_patterns_batch(
                    classifications, batch_name, retry_count + 1, max_retries
                )
            else:
                logger.error(
                    f"    Max retries reached for {batch_name}, returning empty patterns"
                )
                return []

        # Parse JSON
        try:
            json_match = re.search(
                r"```json\s*(\{.+?\})\s*```", response_text, re.DOTALL
            )
            if json_match:
                response_text = json_match.group(1)
            else:
                logger.warning(
                    "    Response did not contain JSON code block, attempting direct parse"
                )

            result = json.loads(response_text)

            if "patterns" not in result:
                logger.error(
                    f"    Response missing 'patterns' key. Keys found: {list(result.keys())}"
                )
                logger.debug(f"    Response (first 500 chars): {response_text[:500]}")
                return []

            patterns = [PatternGroup(**p) for p in result["patterns"]]

            logger.info(
                f"    ✅ Found {len(patterns)} patterns covering {sum(p.ticket_count for p in patterns)} tickets"
            )
            return patterns

        except json.JSONDecodeError as e:
            logger.error(f"    JSON parsing failed: {e}")
            logger.error(f"    Response (first 1000 chars): {response_text[:1000]}")
            return []
        except Exception as e:
            logger.error(f"    Pattern construction failed: {e}")
            logger.error(
                f"    Result keys: {list(result.keys()) if 'result' in locals() else 'N/A'}"
            )
            return []

    async def discover_patterns(
        self,
        classifications: list[TicketClassification],
        batch_size: int = 30,
    ) -> list[PatternGroup]:
        """Identify patterns across ticket classifications using hierarchical batching.

        Strategy:
        1. Group tickets by problem_type
        2. Discover patterns within each problem_type group
        3. Merge patterns across groups

        Args:
            classifications: Ticket classifications from classify_tickets()
            batch_size: Max tickets per Claude SDK call (default: 30)

        Returns:
            List of identified patterns
        """
        from collections import defaultdict

        logger.info(
            f"Discovering patterns across {len(classifications)} tickets (hierarchical batching)"
        )

        # Group by problem_type for better pattern discovery
        by_problem_type: dict[str, list[TicketClassification]] = defaultdict(list)
        for c in classifications:
            by_problem_type[c.problem_type].append(c)

        logger.info(
            f"  Grouped into {len(by_problem_type)} problem types: {list(by_problem_type.keys())}"
        )

        all_patterns = []

        # Process each problem type separately
        for problem_type, tickets in by_problem_type.items():
            logger.info(f"\n  Processing {problem_type}: {len(tickets)} tickets")

            # If problem type has few tickets, discover patterns directly
            if len(tickets) <= batch_size:
                patterns = await self._discover_patterns_batch(
                    tickets, batch_name=f"{problem_type}"
                )
                all_patterns.extend(patterns)
            else:
                # Split large problem type into batches
                logger.info(f"    Large group, splitting into batches of {batch_size}")
                for i in range(0, len(tickets), batch_size):
                    batch = tickets[i : i + batch_size]
                    batch_name = f"{problem_type}_batch_{i // batch_size + 1}"
                    patterns = await self._discover_patterns_batch(
                        batch, batch_name=batch_name
                    )
                    all_patterns.extend(patterns)

        # Deduplicate and merge overlapping patterns
        merged_patterns = self._merge_overlapping_patterns(all_patterns)

        logger.info(
            f"\n✅ Discovered {len(merged_patterns)} patterns covering {sum(p.ticket_count for p in merged_patterns)} tickets"
        )
        return merged_patterns

    def _merge_overlapping_patterns(
        self, patterns: list[PatternGroup]
    ) -> list[PatternGroup]:
        """Merge patterns that have significant ticket overlap.

        Args:
            patterns: List of patterns

        Returns:
            Deduplicated/merged patterns
        """
        if not patterns:
            return []

        # For now, just deduplicate by matched_tickets
        # Future: merge patterns with >50% overlap
        seen_tickets = set()
        unique_patterns = []

        for pattern in patterns:
            pattern_tickets = set(pattern.matched_tickets)

            # Check if this pattern is mostly new tickets
            overlap = len(pattern_tickets & seen_tickets)
            if overlap < len(pattern_tickets) * 0.5:  # <50% overlap
                unique_patterns.append(pattern)
                seen_tickets.update(pattern_tickets)
            else:
                logger.debug(
                    f"  Skipping duplicate pattern {pattern.pattern_id} ({overlap}/{len(pattern_tickets)} tickets already seen)"
                )

        logger.info(
            f"  Merged {len(patterns)} → {len(unique_patterns)} unique patterns"
        )
        return unique_patterns
