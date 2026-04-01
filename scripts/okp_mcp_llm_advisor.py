#!/usr/bin/env python3
"""LLM-powered advisor for okp-mcp boost query suggestions.

Uses Pydantic AI to analyze metrics and suggest code changes for okp-mcp.
Model-agnostic: easily switch between Claude, GPT, Gemini, or local models.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent


class BoostQuerySuggestion(BaseModel):
    """Structured suggestion for boost query changes."""

    reasoning: str = Field(
        description="Why these changes are needed based on the metrics"
    )
    file_path: str = Field(
        description="Relative path to file to edit (e.g., 'src/okp_mcp/portal.py')"
    )
    suggested_change: str = Field(
        description="Specific code change to make (e.g., 'Increase documentKind:solution boost from 2.0 to 4.0')"
    )
    code_snippet: Optional[str] = Field(
        default=None,
        description="Optional Python code snippet showing the exact change"
    )
    expected_improvement: str = Field(
        description="What metrics should improve (e.g., 'URL F1 should increase from 0.33 to >0.7')"
    )
    confidence: str = Field(
        description="Confidence level: high, medium, or low"
    )


class PromptSuggestion(BaseModel):
    """Structured suggestion for system prompt changes."""

    reasoning: str = Field(
        description="Why prompt changes are needed based on the metrics"
    )
    suggested_change: str = Field(
        description="Specific prompt modification to make"
    )
    expected_improvement: str = Field(
        description="What metrics should improve"
    )
    confidence: str = Field(
        description="Confidence level: high, medium, or low"
    )


@dataclass
class MetricSummary:
    """Summary of evaluation metrics for LLM analysis."""

    ticket_id: str
    query: str
    url_f1: Optional[float]
    mrr: Optional[float]
    context_relevance: Optional[float]
    context_precision: Optional[float]
    keywords_score: Optional[float]
    forbidden_claims_score: Optional[float]
    rag_used: bool
    docs_retrieved: bool
    num_docs: int

    def to_prompt_context(self) -> str:
        """Convert metrics to human-readable context for LLM."""
        lines = [
            f"Ticket: {self.ticket_id}",
            f"Query: {self.query}",
            "",
            "RAG Status:",
            f"  - RAG Used: {self.rag_used}",
            f"  - Docs Retrieved: {self.docs_retrieved}",
            f"  - Num Docs: {self.num_docs}",
            "",
            "Retrieval Metrics:",
        ]

        if self.url_f1 is not None:
            lines.append(f"  - URL F1: {self.url_f1:.2f} (threshold: 0.7)")
        if self.mrr is not None:
            lines.append(f"  - MRR: {self.mrr:.2f} (threshold: 0.5)")
        if self.context_relevance is not None:
            lines.append(
                f"  - Context Relevance: {self.context_relevance:.2f} (threshold: 0.7)"
            )
        if self.context_precision is not None:
            lines.append(
                f"  - Context Precision: {self.context_precision:.2f} (threshold: 0.7)"
            )

        lines.append("")
        lines.append("Answer Metrics:")

        if self.keywords_score is not None:
            lines.append(f"  - Keywords: {self.keywords_score:.2f} (threshold: 0.7)")
        if self.forbidden_claims_score is not None:
            lines.append(
                f"  - Forbidden Claims: {self.forbidden_claims_score:.2f} (threshold: 1.0)"
            )

        return "\n".join(lines)


class OkpMcpLLMAdvisor:
    """LLM-powered advisor for okp-mcp improvements."""

    def __init__(
        self,
        model: str = "vertexai:claude-sonnet-4-0",
        okp_mcp_root: Optional[Path] = None,
        project_id: Optional[str] = None,
        region: Optional[str] = "us-east5",
    ):
        """Initialize LLM advisor.

        Args:
            model: Model to use. Examples:
                - "vertexai:claude-sonnet-4-0" (Claude via Vertex AI - default)
                - "vertexai:gemini-2.0-flash" (Gemini via Vertex AI)
                - "claude-sonnet-4-0" (Direct Anthropic)
                - "openai:gpt-4o" (OpenAI)
                - "ollama:llama3" (Local model)
            okp_mcp_root: Path to okp-mcp repository for code context
            project_id: GCP project ID for Vertex AI (optional, uses default project)
            region: GCP region for Vertex AI (default: us-east5)
        """
        self.model = model
        self.okp_mcp_root = okp_mcp_root or (Path.home() / "Work/okp-mcp")
        self.project_id = project_id
        self.region = region

        # Check for Google Cloud credentials
        import os
        if model.startswith("vertexai:"):
            google_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not google_creds:
                print("⚠️  Warning: GOOGLE_APPLICATION_CREDENTIALS not set.")
                print("   Pydantic AI will attempt to use Application Default Credentials (ADC)")
                print("   Run 'gcloud auth application-default login' if authentication fails")

        # For direct Anthropic access
        elif model.startswith("claude"):
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Use 'vertexai:claude-sonnet-4-0' for Vertex AI access instead."
                )

        # Create boost query suggestion agent
        self.boost_agent = Agent(
            model,
            result_type=BoostQuerySuggestion,
            system_prompt="""You are an expert in Solr/Lucene search optimization and boost query tuning.

Your task is to analyze evaluation metrics from an okp-mcp RAG system and suggest specific
boost query improvements to improve document retrieval.

Key context about okp-mcp:
- Uses Solr for document search
- Boost queries modify document scoring based on fields like:
  - documentKind (e.g., solution, article, guide)
  - product (e.g., RHEL, OpenShift)
  - title relevance
  - content type
- Boost values are typically 1.0-10.0 (higher = more important)

When suggesting changes:
1. Be SPECIFIC about what to change (exact field, exact boost value)
2. Explain WHY based on the metrics
3. Predict WHAT should improve
4. Provide confidence level based on how clear the problem is

Common patterns:
- URL F1 = 0.0 → Wrong doc types retrieved, adjust documentKind boost
- Low MRR (< 0.5) → Right docs exist but ranked too low, increase boost
- Low context relevance → Query doesn't match content, may need query reformulation

Always suggest conservative changes first (2x boost increase, not 10x).
""",
        )

        # Create prompt suggestion agent
        self.prompt_agent = Agent(
            model,
            result_type=PromptSuggestion,
            system_prompt="""You are an expert in LLM prompt engineering for RAG systems.

Your task is to analyze evaluation metrics and suggest system prompt improvements
to help the LLM better utilize retrieved documents.

Common issues:
- Keywords missing despite good retrieval → LLM ignoring context, needs stronger instruction
- Hallucination despite context → Need explicit "only use provided context" instruction
- Wrong tone/format → Need specific output formatting instructions

When suggesting changes:
1. Be SPECIFIC about what to add/modify in the prompt
2. Explain WHY based on the metrics
3. Predict WHAT should improve
4. Provide confidence level

Always suggest minimal changes first (add one instruction, not rewrite entire prompt).
""",
        )

    def suggest_boost_query_changes(self, metrics: MetricSummary) -> BoostQuerySuggestion:
        """Suggest boost query improvements based on metrics.

        Args:
            metrics: Evaluation metrics summary

        Returns:
            Structured suggestion for boost query changes
        """
        prompt = f"""Analyze these evaluation metrics and suggest specific boost query changes:

{metrics.to_prompt_context()}

Problem context:
- This is okp-mcp, a RAG system for Red Hat documentation
- Query: "{metrics.query}"
- Current state: {self._diagnosis_text(metrics)}

Suggest ONE specific boost query change to improve retrieval.
Be concrete: which field, which value, why.
"""

        result = self.boost_agent.run_sync(prompt)
        return result.data

    def suggest_prompt_changes(self, metrics: MetricSummary) -> PromptSuggestion:
        """Suggest system prompt improvements based on metrics.

        Args:
            metrics: Evaluation metrics summary

        Returns:
            Structured suggestion for prompt changes
        """
        prompt = f"""Analyze these evaluation metrics and suggest system prompt improvements:

{metrics.to_prompt_context()}

Problem context:
- This is okp-mcp, a RAG system for Red Hat documentation
- Query: "{metrics.query}"
- Current state: {self._diagnosis_text(metrics)}

Suggest ONE specific system prompt change to improve answer quality.
Be concrete: what to add/modify, why.
"""

        result = self.prompt_agent.run_sync(prompt)
        return result.data

    def _diagnosis_text(self, metrics: MetricSummary) -> str:
        """Generate diagnosis text for LLM context."""
        if not metrics.rag_used:
            return "RAG NOT USED - LLM answered from general knowledge"

        if metrics.rag_used and not metrics.docs_retrieved:
            return "RAG CALLED BUT NO DOCUMENTS RETRIEVED"

        if metrics.url_f1 is not None and metrics.url_f1 < 0.7:
            if metrics.url_f1 == 0.0:
                return "RETRIEVAL PROBLEM - Wrong documents retrieved (none of expected docs)"
            return f"RETRIEVAL PROBLEM - Some expected docs missing (F1={metrics.url_f1:.2f})"

        if (
            metrics.url_f1 is not None
            and metrics.url_f1 >= 0.7
            and metrics.keywords_score is not None
            and metrics.keywords_score < 0.7
        ):
            return "ANSWER PROBLEM - Right docs retrieved but keywords missing"

        return "Metrics look good overall"


if __name__ == "__main__":
    import sys

    # Example usage - requires GOOGLE_APPLICATION_CREDENTIALS
    print("=" * 80)
    print("OKP-MCP LLM Advisor - Test Mode")
    print("=" * 80)
    print("\nUsing Vertex AI with Claude Sonnet 4.0")
    print("Authentication: GOOGLE_APPLICATION_CREDENTIALS")
    print()

    try:
        advisor = OkpMcpLLMAdvisor(model="vertexai:claude-sonnet-4-0")
    except Exception as e:
        print(f"❌ Error initializing advisor: {e}")
        print("\nMake sure GOOGLE_APPLICATION_CREDENTIALS is set:")
        print("  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json")
        print("\nOr use Application Default Credentials:")
        print("  gcloud auth application-default login")
        sys.exit(1)

    # Test with sample metrics from RSPEED-2482
    metrics = MetricSummary(
        ticket_id="RSPEED-2482",
        query="Can I run a RHEL 6 container on RHEL 9?",
        url_f1=0.0,
        mrr=0.2,
        context_relevance=0.0,
        context_precision=0.7,
        keywords_score=1.0,
        forbidden_claims_score=1.0,
        rag_used=True,
        docs_retrieved=True,
        num_docs=5,
    )

    print("=" * 80)
    print("BOOST QUERY SUGGESTION")
    print("=" * 80)
    print("\nCalling Claude via Vertex AI...")

    try:
        suggestion = advisor.suggest_boost_query_changes(metrics)
        print(f"\n✅ Success!")
        print(f"\nReasoning: {suggestion.reasoning}")
        print(f"\nFile: {suggestion.file_path}")
        print(f"\nChange: {suggestion.suggested_change}")
        if suggestion.code_snippet:
            print(f"\nCode:\n{suggestion.code_snippet}")
        print(f"\nExpected Improvement: {suggestion.expected_improvement}")
        print(f"\nConfidence: {suggestion.confidence}")
    except Exception as e:
        print(f"\n❌ Error getting suggestion: {e}")
        print("\nThis might be a:")
        print("  - Authentication issue (check GOOGLE_APPLICATION_CREDENTIALS)")
        print("  - API quota issue")
        print("  - Model availability issue")
        sys.exit(1)
