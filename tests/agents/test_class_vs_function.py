#!/usr/bin/env python3
"""Test if class vs function matters for Claude Agent SDK.

TP-006-CLASS: Isolate whether class context causes the issue
"""

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from claude_agent_sdk import query as claude_query, ClaudeAgentOptions


# Test 1: As a standalone async function (like working tests)
async def test_as_function():
    """Test calling Claude SDK from a function."""
    prompt = 'You are a RHEL expert. Answer: What is RHEL 6 EOL date? Return JSON: {"answer": "..."}'

    options = ClaudeAgentOptions(model="claude-sonnet-4-5@20250929", max_turns=1)

    response_text = ""
    async for message in claude_query(prompt=prompt, options=options):
        if hasattr(message, "content"):
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text

    return response_text


# Test 2: As a class method (like Linux Expert)
@dataclass
class TestAgent:
    """Minimal agent class to test if class context matters."""

    model: str = "claude-sonnet-4-5@20250929"

    async def call_claude(self):
        """Call Claude SDK from within a class method."""
        prompt = 'You are a RHEL expert. Answer: What is RHEL 6 EOL date? Return JSON: {"answer": "..."}'

        options = ClaudeAgentOptions(model=self.model, max_turns=1)

        response_text = ""
        async for message in claude_query(prompt=prompt, options=options):
            if hasattr(message, "content"):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text

        return response_text


async def main():
    print("Test 1: Calling Claude SDK from function")
    print("-" * 80)
    try:
        result1 = await test_as_function()
        print(f"✅ Function test PASSED ({len(result1)} chars)")
        print(f"   Preview: {result1[:100]}")
    except Exception as e:
        print(f"❌ Function test FAILED: {e}")
        return False

    print("\nTest 2: Calling Claude SDK from class method")
    print("-" * 80)
    try:
        agent = TestAgent()
        result2 = await agent.call_claude()
        print(f"✅ Class test PASSED ({len(result2)} chars)")
        print(f"   Preview: {result2[:100]}")
    except Exception as e:
        print(f"❌ Class test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
