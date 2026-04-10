"""Test if Application Default Credentials (ADC) are accessible.

Claude Agent SDK uses ADC, not GOOGLE_APPLICATION_CREDENTIALS.
"""

import os
import subprocess
from pathlib import Path

import pytest


def test_adc_file_exists():
    """Verify ADC file exists at expected location."""
    adc_path = Path.home() / ".config/gcloud/application_default_credentials.json"
    assert adc_path.exists(), f"ADC file not found at: {adc_path}"
    print(f"\n✅ ADC file exists: {adc_path}")


def test_adc_readable():
    """Verify ADC file is readable."""
    adc_path = Path.home() / ".config/gcloud/application_default_credentials.json"

    if not adc_path.exists():
        pytest.skip("ADC file doesn't exist")

    # Try to read it
    import json

    with open(adc_path) as f:
        data = json.load(f)

    assert "type" in data, "ADC file missing 'type' field"
    print(f"\n✅ ADC file readable, type: {data.get('type')}")


def test_gcloud_config_accessible():
    """Test if gcloud config is accessible from pytest subprocess."""
    result = subprocess.run(
        ["gcloud", "config", "get", "project"],
        capture_output=True,
        text=True,
    )

    print(f"\n  gcloud exit code: {result.returncode}")
    print(f"  gcloud stdout: {result.stdout.strip()}")
    print(f"  gcloud stderr: {result.stderr.strip()}")

    # Don't fail if gcloud not configured, just report
    if result.returncode == 0:
        print(f"✅ gcloud accessible, project: {result.stdout.strip()}")
    else:
        print("⚠️  gcloud not accessible or not configured")


def test_anthropic_vertex_env_var():
    """Verify ANTHROPIC_VERTEX_PROJECT_ID is set."""
    project_id = os.getenv("ANTHROPIC_VERTEX_PROJECT_ID")
    assert project_id, "ANTHROPIC_VERTEX_PROJECT_ID not set"
    print(f"\n✅ ANTHROPIC_VERTEX_PROJECT_ID: {project_id}")
