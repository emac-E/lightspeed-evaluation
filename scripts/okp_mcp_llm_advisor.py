#!/usr/bin/env python3
"""LLM-powered advisor for okp-mcp boost query suggestions.

Uses Anthropic SDK with Vertex AI to analyze metrics and suggest code changes.
Supports tiered model routing to optimize costs.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from anthropic import AnthropicVertex
from pydantic import BaseModel, Field


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
        description="Optional Python code snippet showing the exact change",
    )
    expected_improvement: str = Field(
        description="What metrics should improve (e.g., 'URL F1 should increase from 0.33 to >0.7')"
    )
    confidence: str = Field(description="Confidence level: high, medium, or low")


class PromptSuggestion(BaseModel):
    """Structured suggestion for system prompt changes."""

    reasoning: str = Field(
        description="Why prompt changes are needed based on the metrics"
    )
    suggested_change: str = Field(description="Specific prompt modification to make")
    expected_improvement: str = Field(description="What metrics should improve")
    confidence: str = Field(description="Confidence level: high, medium, or low")


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
    faithfulness: Optional[float]
    answer_correctness: Optional[float]
    response_relevancy: Optional[float]
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

        if self.faithfulness is not None:
            lines.append(f"  - Faithfulness: {self.faithfulness:.2f} (threshold: 0.8)")
        if self.answer_correctness is not None:
            lines.append(
                f"  - Answer Correctness: {self.answer_correctness:.2f} (threshold: 0.75)"
            )
        if self.response_relevancy is not None:
            lines.append(
                f"  - Response Relevancy: {self.response_relevancy:.2f} (threshold: 0.8)"
            )
        if self.keywords_score is not None:
            lines.append(f"  - Keywords: {self.keywords_score:.2f} (threshold: 0.7)")
        if self.forbidden_claims_score is not None:
            lines.append(
                f"  - Forbidden Claims: {self.forbidden_claims_score:.2f} (threshold: 1.0)"
            )

        return "\n".join(lines)


class OkpMcpLLMAdvisor:
    """LLM-powered advisor for okp-mcp improvements with tiered model routing."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5@20250929",
        okp_mcp_root: Optional[Path] = None,
        project_id: Optional[str] = None,
        region: Optional[str] = None,
        # Tiered model routing
        use_tiered_models: bool = True,
        simple_model: Optional[str] = None,
        complex_model: Optional[str] = None,
    ):
        """Initialize LLM advisor with Anthropic Vertex AI.

        Args:
            model: Default model for medium complexity tasks
            okp_mcp_root: Path to okp-mcp repository for code context
            project_id: GCP project ID (uses ANTHROPIC_VERTEX_PROJECT_ID if not set)
            region: GCP region (uses CLOUD_ML_REGION if not set)
            use_tiered_models: Enable smart model routing
            simple_model: Model for simple tasks (default: claude-haiku-4-5@20251001)
            complex_model: Model for complex tasks (default: same as model)
        """
        self.model = model
        self.okp_mcp_root = okp_mcp_root or (Path.home() / "Work/okp-mcp")
        self.use_tiered_models = use_tiered_models

        # Get Vertex AI credentials from environment
        self.project_id = project_id or os.getenv("ANTHROPIC_VERTEX_PROJECT_ID")
        self.region = region or os.getenv("CLOUD_ML_REGION", "us-east5")

        if not self.project_id:
            raise ValueError(
                "project_id not provided and ANTHROPIC_VERTEX_PROJECT_ID not set"
            )

        # Set up tiered models
        if use_tiered_models:
            self.simple_model = simple_model or "claude-haiku-4-5@20251001"
            self.medium_model = model
            self.complex_model = complex_model or model
        else:
            self.simple_model = model
            self.medium_model = model
            self.complex_model = model

        # Handle custom credentials path to avoid conflicts with other GCP services
        # Check for GOOGLE_CLAUDE_CREDENTIALS first (for Claude/Anthropic Vertex AI)
        # Falls back to GOOGLE_APPLICATION_CREDENTIALS if not set
        claude_creds = os.getenv("GOOGLE_CLAUDE_CREDENTIALS")
        if claude_creds:
            # Temporarily set GOOGLE_APPLICATION_CREDENTIALS for AnthropicVertex client
            original_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = claude_creds
            print(
                f"🔑 Using custom credentials: GOOGLE_CLAUDE_CREDENTIALS={claude_creds}"
            )

        try:
            # Create Anthropic Vertex AI client
            self.client = AnthropicVertex(
                project_id=self.project_id,
                region=self.region,
            )
        finally:
            # Restore original GOOGLE_APPLICATION_CREDENTIALS if we changed it
            if claude_creds:
                if original_creds:
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = original_creds
                else:
                    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

        print(f"✅ Initialized with Vertex AI project: {self.project_id}")
        print(f"   Region: {self.region}")
        if use_tiered_models:
            print(f"   Simple model: {self.simple_model}")
            print(f"   Medium model: {self.medium_model}")
            print(f"   Complex model: {self.complex_model}")

    def _call_with_structured_output(
        self, model: str, system_prompt: str, user_prompt: str, output_schema: dict
    ) -> dict:
        """Call Claude with structured output using tool use.

        Args:
            model: Model to use
            system_prompt: System prompt
            user_prompt: User prompt
            output_schema: JSON schema for output

        Returns:
            Parsed JSON response matching schema
        """
        # Use Claude's tool use for structured outputs
        response = self.client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[
                {
                    "name": "provide_suggestion",
                    "description": "Provide the structured suggestion",
                    "input_schema": output_schema,
                }
            ],
            tool_choice={"type": "tool", "name": "provide_suggestion"},
        )

        # Extract tool use from response
        for content in response.content:
            if content.type == "tool_use" and content.name == "provide_suggestion":
                return content.input

        raise ValueError(f"No tool use found in response: {response}")

    def classify_problem_complexity(self, metrics: MetricSummary) -> str:
        """Quickly classify problem complexity using cheap model.

        Args:
            metrics: Evaluation metrics summary

        Returns:
            "SIMPLE", "MEDIUM", or "COMPLEX"
        """
        if not self.use_tiered_models:
            return "MEDIUM"

        system_prompt = """You are a quick diagnostic classifier.
Analyze metrics and categorize the problem as: SIMPLE, MEDIUM, or COMPLEX.

SIMPLE: Clear pattern, obvious fix
- URL F1 = 0.0 and only 1-2 docs retrieved → clearly wrong doc type
- RAG not used at all → configuration issue

MEDIUM: Needs analysis but straightforward
- URL F1 between 0.3-0.7 → some docs correct, some wrong
- Keywords missing but retrieval good → prompt issue

COMPLEX: Ambiguous or multi-faceted
- All metrics borderline
- Conflicting signals
- Multiple problems at once

Respond with ONLY one word: SIMPLE, MEDIUM, or COMPLEX."""

        user_prompt = f"""Classify this problem:

{metrics.to_prompt_context()}

Is this SIMPLE, MEDIUM, or COMPLEX?"""

        response = self.client.messages.create(
            model=self.simple_model,
            max_tokens=10,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        complexity = response.content[0].text.strip().upper()

        # Validate response
        if complexity not in ["SIMPLE", "MEDIUM", "COMPLEX"]:
            return "MEDIUM"

        return complexity

    def suggest_boost_query_changes(
        self, metrics: MetricSummary, auto_escalate: bool = True
    ) -> BoostQuerySuggestion:
        """Suggest boost query improvements based on metrics.

        Args:
            metrics: Evaluation metrics summary
            auto_escalate: If True and problem is COMPLEX, use more expensive model

        Returns:
            Structured suggestion for boost query changes
        """
        # Classify complexity if tiered models enabled
        model_to_use = self.medium_model
        if self.use_tiered_models and auto_escalate:
            complexity = self.classify_problem_complexity(metrics)
            print(f"  Problem complexity: {complexity}")

            if complexity == "COMPLEX":
                print(f"  Escalating to complex model: {self.complex_model}")
                model_to_use = self.complex_model

        system_prompt = """You are an expert in Solr/Lucene search optimization and boost query tuning.

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

Always suggest conservative changes first (2x boost increase, not 10x)."""

        user_prompt = f"""Analyze these evaluation metrics and suggest specific boost query changes:

{metrics.to_prompt_context()}

Problem context:
- This is okp-mcp, a RAG system for Red Hat documentation
- Query: "{metrics.query}"
- Current state: {self._diagnosis_text(metrics)}

Suggest ONE specific boost query change to improve retrieval.
Be concrete: which field, which value, why."""

        result = self._call_with_structured_output(
            model=model_to_use,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=BoostQuerySuggestion.model_json_schema(),
        )

        return BoostQuerySuggestion(**result)

    def suggest_prompt_changes(
        self, metrics: MetricSummary, auto_escalate: bool = True
    ) -> PromptSuggestion:
        """Suggest system prompt improvements based on metrics.

        Args:
            metrics: Evaluation metrics summary
            auto_escalate: If True and problem is COMPLEX, use more expensive model

        Returns:
            Structured suggestion for prompt changes
        """
        # Classify complexity if tiered models enabled
        model_to_use = self.medium_model
        if self.use_tiered_models and auto_escalate:
            complexity = self.classify_problem_complexity(metrics)
            print(f"  Problem complexity: {complexity}")

            if complexity == "COMPLEX":
                print(f"  Escalating to complex model: {self.complex_model}")
                model_to_use = self.complex_model

        system_prompt = """You are an expert in LLM prompt engineering for RAG systems.

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

Always suggest minimal changes first (add one instruction, not rewrite entire prompt)."""

        user_prompt = f"""Analyze these evaluation metrics and suggest system prompt improvements:

{metrics.to_prompt_context()}

Problem context:
- This is okp-mcp, a RAG system for Red Hat documentation
- Query: "{metrics.query}"
- Current state: {self._diagnosis_text(metrics)}

Suggest ONE specific system prompt change to improve answer quality.
Be concrete: what to add/modify, why."""

        result = self._call_with_structured_output(
            model=model_to_use,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=PromptSuggestion.model_json_schema(),
        )

        return PromptSuggestion(**result)

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

    # Example usage
    print("=" * 80)
    print("OKP-MCP LLM Advisor - Test Mode")
    print("=" * 80)
    print("\nUsing Anthropic SDK with Vertex AI")
    print(
        "Authentication: ANTHROPIC_VERTEX_PROJECT_ID + Application Default Credentials"
    )
    print()

    try:
        advisor = OkpMcpLLMAdvisor(
            model="claude-sonnet-4-5@20250929",
            use_tiered_models=True,
            simple_model="claude-haiku-4-5@20251001",
        )
    except Exception as e:
        print(f"❌ Error initializing advisor: {e}")
        print("\nMake sure:")
        print("  export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id")
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
        faithfulness=0.6,
        answer_correctness=0.80,
        response_relevancy=0.7,
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
        print("\n✅ Success!")
        print(f"\nReasoning: {suggestion.reasoning}")
        print(f"\nFile: {suggestion.file_path}")
        print(f"\nChange: {suggestion.suggested_change}")
        if suggestion.code_snippet:
            print(f"\nCode:\n{suggestion.code_snippet}")
        print(f"\nExpected Improvement: {suggestion.expected_improvement}")
        print(f"\nConfidence: {suggestion.confidence}")
    except Exception as e:
        print(f"\n❌ Error getting suggestion: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
