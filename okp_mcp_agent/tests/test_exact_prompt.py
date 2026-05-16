#!/usr/bin/env python3
"""Test the exact prompt that Linux Expert uses.

TP-006-EXACT: Test exact same prompt structure as _form_hypothesis
"""

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from claude_agent_sdk import query as claude_query, ClaudeAgentOptions


async def test_exact_linux_expert_prompt():
    """Test exact same prompt format as Linux Expert._form_hypothesis."""

    # EXACT same system prompt from Linux Expert
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

    # EXACT same format as Linux Expert combines prompts
    key = "RSPEED-2482"
    summary = "Incorrect answer: Can I run a RHEL 6 container on RHEL 9?"
    description = "User asked about RHEL 6 container support. CLA said it's supported. This is wrong."

    full_prompt = f"""{system_prompt}

---

Analyze this JIRA ticket:

Ticket: {key}
Summary: {summary}
Description: {description}

Extract the user query, form your hypothesis about the correct answer, and generate verification queries to check facts in RHEL documentation.

Return your response as JSON only."""

    print(f"Prompt length: {len(full_prompt)} characters")
    print(f"First 200 chars: {full_prompt[:200]}...")
    print(f"Last 200 chars: ...{full_prompt[-200:]}")
    print("\nCalling Claude Agent SDK...")

    # EXACT same options as Linux Expert
    options = ClaudeAgentOptions(
        model="claude-sonnet-4-5@20250929",
        max_turns=1,
    )

    # EXACT same iteration pattern
    response_text = ""
    async for message in claude_query(prompt=full_prompt, options=options):
        if hasattr(message, "content"):
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text

    print(f"\n✅ Got response ({len(response_text)} chars)")
    print(f"Response preview: {response_text[:500]}...")

    # Parse JSON
    json_match = re.search(r"```json\s*(\{.+?\})\s*```", response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
        result = json.loads(json_str)
        print(f"\n✅ Parsed JSON successfully")
        print(f"Keys: {result.keys()}")
        return result
    else:
        print(f"\n❌ No JSON found in response")
        return None


if __name__ == "__main__":
    result = asyncio.run(test_exact_linux_expert_prompt())
    if result:
        print("\n✅ TEST PASSED")
    else:
        print("\n❌ TEST FAILED")
        sys.exit(1)
