#!/usr/bin/env python3
"""Test model escalation from Sonnet to Opus.

Purpose: Debug why Opus fails in okp_mcp_agent escalation workflow.

Tests:
- TE-001: Sonnet baseline (should work)
- TE-002: Opus direct call (test if Opus works at all)
- TE-003: Escalation workflow (Sonnet → Opus on failure)
- TE-004: Opus with file editing (matches okp_mcp_llm_advisor usage)
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

from claude_agent_sdk import query as claude_query, ClaudeAgentOptions, AssistantMessage


# Model tier configuration
# NOTE: Using 4.6 models (not 4.5) - these are the actual available models
TIER_MODELS = {
    "medium": "claude-sonnet-4-6",
    "complex": "claude-opus-4-6",  # This is what your friend uses
}


@pytest.mark.asyncio
async def test_te001_sonnet_baseline():
    """TE-001: Verify Sonnet works as baseline.

    This should succeed - establishes that environment is working.
    """
    print("\n" + "="*80)
    print("TE-001: Sonnet Baseline Test")
    print("="*80)

    # Check environment
    project_id = os.getenv("ANTHROPIC_VERTEX_PROJECT_ID")
    assert project_id, "ANTHROPIC_VERTEX_PROJECT_ID not set"

    prompt = "You are a code analyst. Analyze this config and respond with 'ANALYZED' if you understand."

    options = ClaudeAgentOptions(
        model=TIER_MODELS["medium"],
        max_turns=1,
    )

    # CRITICAL: Temporarily unset GOOGLE_APPLICATION_CREDENTIALS
    # Claude SDK uses ADC, but GOOGLE_APPLICATION_CREDENTIALS (for Gemini) confuses it
    saved_google_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

    response_text = ""
    try:
        async for message in claude_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text

        print(f"✅ Sonnet response: {response_text[:200]}")
        assert response_text, "No response from Sonnet"
        return True
    except Exception as e:
        print(f"❌ Sonnet failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        # Restore GOOGLE_APPLICATION_CREDENTIALS
        if saved_google_creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved_google_creds


@pytest.mark.asyncio
async def test_te002_opus_direct():
    """TE-002: Test Opus directly.

    Tests if Opus model works at all with simple prompt.
    If this fails, Opus is not accessible or configured incorrectly.
    """
    print("\n" + "="*80)
    print("TE-002: Opus Direct Test")
    print("="*80)

    # Check environment
    project_id = os.getenv("ANTHROPIC_VERTEX_PROJECT_ID")
    assert project_id, "ANTHROPIC_VERTEX_PROJECT_ID not set"

    prompt = "You are a code analyst. Analyze this config and respond with 'ANALYZED' if you understand."

    options = ClaudeAgentOptions(
        model=TIER_MODELS["complex"],  # Use Opus
        max_turns=1,
    )

    # CRITICAL: Unset GOOGLE_APPLICATION_CREDENTIALS (same as TE-001)
    saved_google_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

    response_text = ""
    try:
        print(f"🔍 Attempting to call Opus: {TIER_MODELS['complex']}")
        async for message in claude_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text
                        print(f"📝 Received text block: {block.text[:100]}")

        print(f"✅ Opus response: {response_text[:200]}")
        assert response_text, "No response from Opus"
        return True
    except Exception as e:
        print(f"❌ Opus failed: {type(e).__name__}: {e}")
        error_msg = str(e)
        print(f"   Error message: {error_msg}")

        # Check for specific error patterns
        if "Command failed with exit code 1" in error_msg:
            print("   ⚠️  This is the 'exit code 1' error from okp_mcp_agent!")
        if "permission" in error_msg.lower():
            print("   ⚠️  Possible permissions issue")
        if "quota" in error_msg.lower() or "rate" in error_msg.lower():
            print("   ⚠️  Possible quota/rate limit issue")
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
            print("   ⚠️  Model not found - may not be available in this region/project")

        import traceback
        traceback.print_exc()
        raise
    finally:
        # Restore GOOGLE_APPLICATION_CREDENTIALS
        if saved_google_creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved_google_creds


@pytest.mark.asyncio
async def test_te003_escalation_workflow():
    """TE-003: Test escalation workflow (Sonnet → Opus on simulated failure).

    Simulates the okp_mcp_agent workflow:
    1. Try Sonnet first
    2. If "complexity" is high, escalate to Opus
    3. If Opus fails, fall back to Sonnet
    """
    print("\n" + "="*80)
    print("TE-003: Escalation Workflow Test")
    print("="*80)

    # CRITICAL: Unset GOOGLE_APPLICATION_CREDENTIALS
    saved_google_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

    try:
        # Simulate a "complex" problem that would trigger escalation
        complexity = "COMPLEX"

        prompt = """Analyze this Solr configuration and suggest improvements:

qf: title^4.0 main_content^2.0
pf: title^8.0
mm: 2<-1 5<60%

Expected docs not ranking well. What should change?"""

        # Start with medium model
        current_tier = "medium"

        # Classify as complex (simulate)
        if complexity == "COMPLEX":
            print(f"  Problem classified as COMPLEX - escalating to Opus")
            current_tier = "complex"

        current_model = TIER_MODELS[current_tier]
        print(f"  Using model: {current_model} (tier: {current_tier})")

        options = ClaudeAgentOptions(
            model=current_model,
            max_turns=3,
        )

        response_text = ""
        opus_failed = False
        async for message in claude_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text

        print(f"✅ {current_tier} model succeeded: {response_text[:200]}")
        return True

    except Exception as e:
        error_msg = str(e)
        print(f"❌ {current_tier} model failed: {type(e).__name__}: {e}")

        # Check if this is the Opus failure pattern
        if "Command failed with exit code 1" in error_msg and current_tier == "complex":
            print("  ⚠️  Opus failed with exit code 1 - falling back to Sonnet")
            opus_failed = True

            # Fallback to Sonnet (matches okp_mcp_llm_advisor.py lines 832-841)
            print(f"  Retrying with {TIER_MODELS['medium']}...")
            current_tier = "medium"
            current_model = TIER_MODELS[current_tier]

            options = ClaudeAgentOptions(
                model=current_model,
                max_turns=3,
            )

            response_text = ""
            async for message in claude_query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "text"):
                            response_text += block.text

            print(f"✅ Fallback to Sonnet succeeded: {response_text[:200]}")
            return True
        else:
            # Some other error
            import traceback
            traceback.print_exc()
            raise
    finally:
        # Restore GOOGLE_APPLICATION_CREDENTIALS
        if saved_google_creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved_google_creds


@pytest.mark.asyncio
async def test_te004_opus_with_file_editing():
    """TE-004: Test Opus with file editing tools (matches okp_mcp_llm_advisor).

    This is the EXACT usage pattern from okp_mcp_llm_advisor.py.
    Tests if Opus fails specifically when file editing is enabled.
    """
    print("\n" + "="*80)
    print("TE-004: Opus with File Editing Tools")
    print("="*80)

    # Create a temporary directory for testing
    import tempfile
    test_dir = Path(tempfile.mkdtemp(prefix="test_opus_"))
    print(f"  Test directory: {test_dir}")

    # Create a test file to edit
    test_file = test_dir / "test_config.py"
    test_file.write_text("""# Test Solr config
qf = "title^4.0 main_content^2.0"
pf = "title^8.0"
mm = "2<-1 5<60%"
""")

    print(f"  Created test file: {test_file}")

    prompt = f"""You are a Solr optimization expert.

Read the file test_config.py and suggest an improvement.

STEP 1: Use the Read tool to read test_config.py
STEP 2: Use the Edit tool to change one boost value
STEP 3: Provide a JSON summary of your change:

```json
{{
  "reasoning": "why you made this change",
  "file_path": "test_config.py",
  "suggested_change": "what you changed",
  "confidence": "high"
}}
```"""

    # Temporarily unset GOOGLE_APPLICATION_CREDENTIALS (matches okp_mcp_llm_advisor.py line 420)
    saved_google_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

    try:
        options = ClaudeAgentOptions(
            model=TIER_MODELS["complex"],  # Use Opus
            allowed_tools=["Read", "Edit", "Glob", "Grep"],  # Enable file editing
            permission_mode="acceptEdits",  # Auto-approve edits
            max_turns=20,
            cwd=str(test_dir),  # Work in test directory
        )

        print(f"🔍 Calling Opus with file editing enabled...")
        print(f"   Model: {TIER_MODELS['complex']}")
        print(f"   Tools: Read, Edit, Glob, Grep")
        print(f"   CWD: {test_dir}")

        response_text = ""
        async for message in claude_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_text += block.text
                        print(f"📝 Text block: {block.text[:100]}")

        print(f"✅ Opus with file editing succeeded")
        print(f"   Response: {response_text[:300]}")

        # Check if file was modified
        modified_content = test_file.read_text()
        print(f"   File modified: {modified_content != test_file.read_text()}")

        return True

    except Exception as e:
        print(f"❌ Opus with file editing failed: {type(e).__name__}: {e}")
        error_msg = str(e)

        # Detailed error analysis
        print("\n" + "="*80)
        print("ERROR ANALYSIS:")
        print("="*80)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {error_msg}")

        if "Command failed with exit code 1" in error_msg:
            print("\n⚠️  THIS IS THE EXACT ERROR FROM okp_mcp_agent!")
            print("   Opus fails when file editing tools are enabled.")
            print("   Checking possible causes:")
            print("   - Model availability in region?")
            print("   - Permissions for file operations?")
            print("   - API quota/rate limits?")

        import traceback
        traceback.print_exc()

        # Don't raise - we want to see this error
        return False

    finally:
        # Restore GOOGLE_APPLICATION_CREDENTIALS
        if saved_google_creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved_google_creds

        # Cleanup test directory
        import shutil
        shutil.rmtree(test_dir)


if __name__ == "__main__":
    print("Model Escalation Debug Tests")
    print("="*80)
    print(f"Medium model: {TIER_MODELS['medium']}")
    print(f"Complex model: {TIER_MODELS['complex']}")
    print("="*80)

    async def run_tests():
        """Run all tests in sequence."""
        results = {}

        # TE-001: Sonnet baseline (should pass)
        try:
            await test_te001_sonnet_baseline()
            results["TE-001"] = "PASS"
        except Exception as e:
            results["TE-001"] = f"FAIL: {e}"

        # TE-002: Opus direct (may fail - this is what we're debugging)
        try:
            await test_te002_opus_direct()
            results["TE-002"] = "PASS"
        except Exception as e:
            results["TE-002"] = f"FAIL: {e}"

        # TE-003: Escalation workflow (tests fallback)
        try:
            await test_te003_escalation_workflow()
            results["TE-003"] = "PASS"
        except Exception as e:
            results["TE-003"] = f"FAIL: {e}"

        # TE-004: Opus with file editing (most likely to fail)
        try:
            await test_te004_opus_with_file_editing()
            results["TE-004"] = "PASS"
        except Exception as e:
            results["TE-004"] = f"FAIL: {e}"

        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        for test_id, result in results.items():
            status = "✅" if result == "PASS" else "❌"
            print(f"{status} {test_id}: {result}")

        print("\n" + "="*80)
        print("DIAGNOSIS:")
        print("="*80)

        if results["TE-001"] == "PASS" and "FAIL" in results.get("TE-002", ""):
            print("❌ Opus is NOT accessible (fails even with simple prompt)")
            print("   Possible causes:")
            print("   - Model not available in your GCP region")
            print("   - Vertex AI API quota exceeded")
            print("   - Model name incorrect or deprecated")
            print("   - Permissions issue with service account")

        if results["TE-002"] == "PASS" and "FAIL" in results.get("TE-004", ""):
            print("⚠️  Opus works with simple prompts but FAILS with file editing")
            print("   Possible causes:")
            print("   - File editing tools not compatible with Opus")
            print("   - CWD/permissions issue when tools are enabled")
            print("   - max_turns too high for Opus quota")

        if all(r == "PASS" for r in results.values()):
            print("✅ All tests passed - Opus escalation should work!")

        return results

    results = asyncio.run(run_tests())

    # Exit with error if any test failed
    sys.exit(0 if all(r == "PASS" for r in results.values()) else 1)
