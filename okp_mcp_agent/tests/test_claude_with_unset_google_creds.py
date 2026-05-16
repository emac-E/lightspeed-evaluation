"""Test if GOOGLE_APPLICATION_CREDENTIALS conflicts with Claude Agent SDK.

Hypothesis: Having GOOGLE_APPLICATION_CREDENTIALS set confuses Claude SDK
which should use ADC instead.
"""

import os

import pytest
from claude_agent_sdk import query as claude_query, ClaudeAgentOptions


@pytest.mark.asyncio
async def test_claude_with_google_creds_unset():
    """Test Claude SDK with GOOGLE_APPLICATION_CREDENTIALS temporarily unset.

    Claude SDK should use ADC, not GOOGLE_APPLICATION_CREDENTIALS.
    """
    # Save and unset GOOGLE_APPLICATION_CREDENTIALS
    saved = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

    try:
        prompt = "Say hello in one sentence."
        options = ClaudeAgentOptions(model="claude-sonnet-4-5@20250929", max_turns=1)

        response_text = ""
        async for message in claude_query(prompt=prompt, options=options):
            if hasattr(message, "content"):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text

        assert response_text, "No response"
        assert "hello" in response_text.lower()
        print(f"\n✅ SUCCESS with GOOGLE_APPLICATION_CREDENTIALS unset")
        print(f"   Response: {response_text[:100]}")

    finally:
        # Restore
        if saved:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved
