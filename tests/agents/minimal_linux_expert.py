"""Minimal Linux Expert - same code but outside src/ directory.

TP-006-LOCATION: Test if src/ location causes the issue
"""

import json
import re
from dataclasses import dataclass

from claude_agent_sdk import query as claude_query, ClaudeAgentOptions


@dataclass
class MinimalLinuxExpert:
    """Minimal version of Linux Expert to test location theory."""

    model: str = "claude-sonnet-4-5@20250929"

    async def form_hypothesis(self, key: str, summary: str, description: str):
        """Same as LinuxExpertAgent._form_hypothesis but in tests/ directory."""
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

        full_prompt = f"""{system_prompt}

---

Analyze this JIRA ticket:

Ticket: {key}
Summary: {summary}
Description: {description}

Extract the user query, form your hypothesis about the correct answer, and generate verification queries to check facts in RHEL documentation.

Return your response as JSON only."""

        options = ClaudeAgentOptions(
            model=self.model,
            max_turns=1,
        )

        response_text = ""
        async for message in claude_query(prompt=full_prompt, options=options):
            if hasattr(message, "content"):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text

        json_match = re.search(r"```json\s*(\{.+?\})\s*```", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)

        return json.loads(response_text)
