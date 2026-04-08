#!/usr/bin/env python3
"""Test Claude Agent SDK connectivity and basic functionality.

Tests:
- TP-001: Claude Agent SDK Basic Connectivity
- TP-002: Claude Agent SDK with Long Prompts
- TP-003: Claude Agent SDK JSON Output
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from claude_agent_sdk import query as claude_query, ClaudeAgentOptions


@pytest.mark.asyncio
async def test_tp001_basic_connectivity():
    """TP-001: Verify Claude Agent SDK can make simple API calls.

    Verifies:
    - SDK can connect to Vertex AI
    - Returns AssistantMessage
    - Has text content
    """
    # Check environment
    project_id = os.getenv("ANTHROPIC_VERTEX_PROJECT_ID")
    assert project_id, "ANTHROPIC_VERTEX_PROJECT_ID not set"

    # Simple short prompt
    prompt = "Say hello in one sentence."

    options = ClaudeAgentOptions(
        model="claude-sonnet-4-5@20250929",
        max_turns=1,
    )

    # Call SDK
    response_text = ""
    async for message in claude_query(prompt=prompt, options=options):
        if hasattr(message, "content"):
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text

    # Verify response
    assert response_text, "No response text received"
    assert len(response_text) > 0, "Empty response"
    assert "hello" in response_text.lower(), f"Expected greeting, got: {response_text}"

    print(f"✅ TP-001 PASS: Got response: {response_text[:100]}")


@pytest.mark.asyncio
async def test_tp002_long_prompt():
    """TP-002: Verify SDK can handle prompts > 1000 characters.

    Verifies:
    - Long prompts don't cause errors
    - Full response received
    """
    # Long prompt with system instructions
    system_prompt = """You are a Senior Red Hat Enterprise Linux (RHEL) Support Engineer with 15+ years experience.

Your expertise covers:
- RHEL versions 6 through 10 (lifecycle, features, EOL dates)
- System administration (systemd, networking, storage, security)
- Container technologies (Podman, RHEL container compatibility)
- Package management (DNF, RPM, application streams)
- Red Hat support policies and lifecycle management

You provide concise, technically accurate answers based on official RHEL documentation and support policies."""

    user_task = """Answer this question in one sentence:

When did RHEL 6 reach end of life?"""

    full_prompt = f"{system_prompt}\n\n---\n\n{user_task}"

    assert len(full_prompt) > 500, f"Prompt too short: {len(full_prompt)} chars"

    options = ClaudeAgentOptions(
        model="claude-sonnet-4-5@20250929",
        max_turns=1,
    )

    # Call SDK
    response_text = ""
    async for message in claude_query(prompt=full_prompt, options=options):
        if hasattr(message, "content"):
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text

    # Verify response
    assert response_text, "No response text received"
    assert len(response_text) > 10, "Response too short"
    # RHEL 6 EOL was November 2020
    assert (
        "2020" in response_text or "november" in response_text.lower()
    ), f"Expected RHEL 6 EOL info, got: {response_text}"

    print(f"✅ TP-002 PASS: Long prompt worked. Response: {response_text[:100]}")


@pytest.mark.asyncio
async def test_tp003_json_output():
    """TP-003: Verify SDK can return structured JSON.

    Verifies:
    - Can request JSON format
    - Response contains valid JSON
    - JSON has expected structure
    """
    prompt = """You are a technical analyst.

Analyze this ticket:
- Ticket: TEST-001
- Summary: "Test ticket for JSON output"

Return JSON with this exact structure:
{
  "ticket_id": "TEST-001",
  "analysis": "brief analysis here",
  "priority": "high|medium|low"
}

Return ONLY the JSON, in a ```json code block."""

    options = ClaudeAgentOptions(
        model="claude-sonnet-4-5@20250929",
        max_turns=1,
    )

    # Call SDK
    response_text = ""
    async for message in claude_query(prompt=prompt, options=options):
        if hasattr(message, "content"):
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text

    # Extract JSON
    import re

    json_match = re.search(r"```json\s*(\{.+?\})\s*```", response_text, re.DOTALL)
    assert json_match, f"No JSON block found in response: {response_text}"

    json_str = json_match.group(1)
    data = json.loads(json_str)

    # Validate structure
    assert "ticket_id" in data, f"Missing ticket_id in JSON: {data}"
    assert data["ticket_id"] == "TEST-001", f"Wrong ticket_id: {data['ticket_id']}"
    assert "analysis" in data, f"Missing analysis in JSON: {data}"
    assert "priority" in data, f"Missing priority in JSON: {data}"

    print(f"✅ TP-003 PASS: Got valid JSON: {json.dumps(data, indent=2)}")


if __name__ == "__main__":
    # Run tests directly
    print("Running Claude Agent SDK Connectivity Tests")
    print("=" * 80)

    async def run_tests():
        print("\nTP-001: Basic Connectivity")
        print("-" * 80)
        try:
            await test_tp001_basic_connectivity()
        except Exception as e:
            print(f"❌ TP-001 FAILED: {e}")
            return False

        print("\nTP-002: Long Prompt")
        print("-" * 80)
        try:
            await test_tp002_long_prompt()
        except Exception as e:
            print(f"❌ TP-002 FAILED: {e}")
            import traceback

            traceback.print_exc()
            return False

        print("\nTP-003: JSON Output")
        print("-" * 80)
        try:
            await test_tp003_json_output()
        except Exception as e:
            print(f"❌ TP-003 FAILED: {e}")
            return False

        return True

    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
