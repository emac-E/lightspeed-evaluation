"""Search Intelligence Manager - Shares search knowledge between extraction and fixing.

This module enables the Solr Expert (during JIRA extraction) to record what searches
work, which documents are found, and what queries fail. This intelligence is then
used by the fixing agent (okp_mcp_agent) to:

- Know which docs SHOULD be retrievable (they were found before)
- See what queries successfully retrieved those docs
- Get better fix suggestions based on proven working searches

Benefits:
- Faster diagnosis (know immediately if it's a search config vs documentation gap)
- Better fixes (use proven working queries as reference)
- Feedback loop (extraction improves fixing, fixing improves future extraction)
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Record of a Solr search attempt.

    Logged by SolrExpertAgent during JIRA extraction verification.
    """

    query: str
    topic: str  # e.g., "RHEL_6_EOL", "CONTAINER_COMPATIBILITY"
    timestamp: str
    ticket_key: str

    # Results
    found_docs: list[dict[str, Any]]
    doc_count: int
    top_doc_score: float

    # Verification context
    verification_confidence: str  # HIGH|MEDIUM|LOW

    # Solr config (for tracking improvements over time)
    solr_config_hash: Optional[str] = None

    @classmethod
    def from_verification(
        cls,
        query: str,
        topic: str,
        ticket_key: str,
        found_docs: list[dict[str, Any]],
        confidence: str,
    ) -> "SearchResult":
        """Create from Solr verification results."""
        return cls(
            query=query,
            topic=topic,
            timestamp=datetime.utcnow().isoformat(),
            ticket_key=ticket_key,
            found_docs=found_docs,
            doc_count=len(found_docs),
            top_doc_score=found_docs[0].get("score", 0.0) if found_docs else 0.0,
            verification_confidence=confidence,
        )


@dataclass
class SearchIntelligenceManager:
    """Manages search intelligence shared between extraction and fixing flows.

    Storage structure:
        search_intelligence/
        ├── search_results.jsonl          # All search attempts (audit trail)
        ├── successful_queries.json       # Queries that found docs (HIGH/MEDIUM)
        └── topic_to_docs.json           # Topic → best docs mapping
    """

    db_path: Path

    def __post_init__(self):
        """Initialize database files."""
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.results_file = self.db_path / "search_results.jsonl"
        self.successful_queries_file = self.db_path / "successful_queries.json"
        self.topic_docs_file = self.db_path / "topic_to_docs.json"

        logger.info(f"Search intelligence database: {self.db_path}")

    def log_search(self, result: SearchResult) -> None:
        """Log a search result from Solr Expert.

        Called during JIRA extraction when Solr Expert verifies claims.

        Args:
            result: Search result to log
        """
        # Append to JSONL log (complete audit trail)
        with open(self.results_file, "a") as f:
            f.write(json.dumps(asdict(result)) + "\n")

        # Index successful searches for quick lookup
        if result.verification_confidence in ["HIGH", "MEDIUM"]:
            self._index_successful_query(result)
            self._index_topic_docs(result)

        logger.debug(
            f"Logged search: {result.query} → {result.doc_count} docs ({result.verification_confidence})"
        )

    def _index_successful_query(self, result: SearchResult) -> None:
        """Track queries that successfully found docs."""
        successful = self._load_json(self.successful_queries_file, {})

        if result.topic not in successful:
            successful[result.topic] = []

        successful[result.topic].append(
            {
                "query": result.query,
                "doc_count": result.doc_count,
                "top_score": result.top_doc_score,
                "confidence": result.verification_confidence,
                "ticket": result.ticket_key,
                "timestamp": result.timestamp,
            }
        )

        self._save_json(self.successful_queries_file, successful)

    def _index_topic_docs(self, result: SearchResult) -> None:
        """Map topics to their authoritative documents."""
        topic_docs = self._load_json(self.topic_docs_file, {})

        if result.topic not in topic_docs:
            topic_docs[result.topic] = {
                "best_docs": [],
                "working_queries": [],
                "last_verified": result.timestamp,
            }

        # Track best docs for this topic (deduplicate by URL)
        existing_urls = {doc["url"] for doc in topic_docs[result.topic]["best_docs"]}
        for doc in result.found_docs[:5]:  # Top 5 per search
            if doc["url"] not in existing_urls:
                topic_docs[result.topic]["best_docs"].append(
                    {
                        "url": doc["url"],
                        "title": doc.get("title", "Untitled"),
                        "score": doc.get("score", 0.0),
                    }
                )
                existing_urls.add(doc["url"])

        # Track working queries (deduplicate)
        if result.query not in topic_docs[result.topic]["working_queries"]:
            topic_docs[result.topic]["working_queries"].append(result.query)

        topic_docs[result.topic]["last_verified"] = result.timestamp

        self._save_json(self.topic_docs_file, topic_docs)

    def get_search_intelligence_for_ticket(
        self,
        ticket_key: str,
        expected_urls: list[str],
    ) -> Optional[dict[str, Any]]:
        """Get search intelligence to help fix a failing ticket.

        Called by okp_mcp_agent when diagnosing URL retrieval failures.

        Args:
            ticket_key: JIRA ticket being debugged
            expected_urls: URLs that should have been retrieved but weren't

        Returns:
            Intelligence about previous successful searches, or None if no matches
        """
        topic_docs = self._load_json(self.topic_docs_file, {})

        # Find topics containing any of the expected URLs
        relevant_topics = []
        for topic, data in topic_docs.items():
            for doc in data["best_docs"]:
                # Check if any expected URL matches
                if any(
                    expected_url.strip().rstrip("/") in doc["url"]
                    or doc["url"] in expected_url
                    for expected_url in expected_urls
                ):
                    relevant_topics.append(
                        {
                            "topic": topic,
                            "working_queries": data["working_queries"],
                            "best_docs": data["best_docs"],
                            "last_verified": data.get("last_verified"),
                        }
                    )
                    break

        if not relevant_topics:
            return None

        return {
            "found": True,
            "message": "These docs were previously retrieved successfully during JIRA extraction",
            "topics": relevant_topics,
            "recommendation": (
                "The expected docs ARE retrievable. Compare current query/config "
                "with these working queries to identify the issue."
            ),
        }

    def get_working_queries_for_topic(self, topic: str) -> list[str]:
        """Get queries that successfully retrieved docs for a topic.

        Args:
            topic: Topic identifier (e.g., "RHEL_6_EOL")

        Returns:
            List of working queries
        """
        topic_docs = self._load_json(self.topic_docs_file, {})
        return topic_docs.get(topic, {}).get("working_queries", [])

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about search intelligence database.

        Returns:
            Statistics summary
        """
        # Count total searches
        total_searches = 0
        if self.results_file.exists():
            with open(self.results_file) as f:
                total_searches = sum(1 for _ in f)

        # Count successful queries
        successful = self._load_json(self.successful_queries_file, {})
        topics_covered = len(successful)
        total_successful = sum(len(queries) for queries in successful.values())

        # Count unique docs
        topic_docs = self._load_json(self.topic_docs_file, {})
        unique_docs = len(
            {
                doc["url"]
                for topic_data in topic_docs.values()
                for doc in topic_data["best_docs"]
            }
        )

        return {
            "total_searches": total_searches,
            "topics_covered": topics_covered,
            "successful_queries": total_successful,
            "unique_docs_found": unique_docs,
            "db_path": str(self.db_path),
        }

    def _load_json(self, path: Path, default: dict) -> dict:
        """Load JSON file with default fallback."""
        if not path.exists():
            return default
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Corrupted JSON file: {path}, using default")
            return default

    def _save_json(self, path: Path, data: dict) -> None:
        """Save JSON file atomically."""
        # Write to temp file first
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(data, f, indent=2)

        # Atomic rename
        temp_path.replace(path)
