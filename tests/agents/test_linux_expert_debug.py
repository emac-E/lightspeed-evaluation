#!/usr/bin/env python3
"""Debug Linux Expert hypothesis formation with stderr capture.

TP-006-DEBUG: Capture actual error from Claude CLI subprocess
"""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lightspeed_evaluation.agents.linux_expert import LinuxExpertAgent


async def test_with_stderr_capture():
    """Capture stderr from Claude CLI to see actual error."""
    agent = LinuxExpertAgent()

    ticket_key = "RSPEED-2482"
    summary = "Incorrect answer: Can I run a RHEL 6 container on RHEL 9?"
    description = "User asked about RHEL 6 container support."

    print("Calling _form_hypothesis...")
    print(f"Working directory: {Path.cwd()}")

    # Check .claude_config.json exists
    home = Path.home()
    config_file = home / ".claude_config.json"
    if config_file.exists():
        print(f"✓ Found {config_file}")
    else:
        print(f"✗ Missing {config_file}")

    try:
        result = await agent._form_hypothesis(ticket_key, summary, description)
        print(f"SUCCESS: {result}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print(f"Error type: {type(e)}")

        # Try to find Claude CLI logs
        claude_dirs = [
            home / ".cache/claude",
            home / ".claude",
            Path("/tmp"),
        ]

        print("\nLooking for Claude CLI logs...")
        for d in claude_dirs:
            if d.exists():
                log_files = list(d.glob("**/*log*")) + list(d.glob("**/*err*"))
                if log_files:
                    print(f"\nFound logs in {d}:")
                    for log in log_files[:5]:  # First 5
                        print(f"  - {log}")
                        try:
                            content = log.read_text()
                            if len(content) > 0:
                                print(f"    Last 500 chars: {content[-500:]}")
                        except:
                            pass

        raise


if __name__ == "__main__":
    asyncio.run(test_with_stderr_capture())
