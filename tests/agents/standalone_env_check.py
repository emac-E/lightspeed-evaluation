"""Standalone script to capture environment (for comparison with pytest)."""

import os
import sys
from pathlib import Path


def get_environment_snapshot():
    """Capture current environment state."""
    return {
        "cwd": str(Path.cwd()),
        "home": str(Path.home()),
        "sys_path": sys.path[:5],
        "env_vars": {
            "ANTHROPIC_VERTEX_PROJECT_ID": os.getenv("ANTHROPIC_VERTEX_PROJECT_ID"),
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv(
                "GOOGLE_APPLICATION_CREDENTIALS"
            ),
            "GOOGLE_CLOUD_PROJECT": os.getenv("GOOGLE_CLOUD_PROJECT"),
            "PATH": os.getenv("PATH", "")[:200],
            "PYTHONPATH": os.getenv("PYTHONPATH"),
            "PYTEST_CURRENT_TEST": os.getenv("PYTEST_CURRENT_TEST"),
        },
        "process": {
            "pid": os.getpid(),
            "ppid": os.getppid(),
        },
    }


if __name__ == "__main__":
    snapshot = get_environment_snapshot()

    output_file = Path("/tmp/standalone_env.txt")
    with open(output_file, "w") as f:
        f.write("=== STANDALONE ENVIRONMENT ===\n\n")
        for key, value in snapshot.items():
            f.write(f"{key}:\n")
            if isinstance(value, dict):
                for k, v in value.items():
                    f.write(f"  {k}: {v}\n")
            else:
                f.write(f"  {value}\n")
            f.write("\n")

    print(f"✅ Environment snapshot saved to: {output_file}")
    print("\nKey findings:")
    print(f"  CWD: {snapshot['cwd']}")
    print(
        f"  ANTHROPIC_VERTEX_PROJECT_ID: {snapshot['env_vars']['ANTHROPIC_VERTEX_PROJECT_ID']}"
    )
    print(f"  PYTEST_CURRENT_TEST: {snapshot['env_vars']['PYTEST_CURRENT_TEST']}")
