#!/usr/bin/env python3
"""Convert okp-mcp functional test cases to lightspeed-evaluation YAML format.

This script reads FunctionalCase definitions from okp-mcp's test suite and
converts them to the evaluation framework's YAML format, enabling:
- Quantitative metrics (F1, MRR, context relevance) vs binary pass/fail
- Multi-run stability analysis
- Cross-suite overfitting detection
- Agentic iteration with structured feedback

Usage:
    python scripts/convert_functional_cases_to_eval.py \
        --input ~/Work/okp-mcp/tests/functional_cases.py \
        --output config/okp_mcp_test_suites/functional_tests.yaml

    # With specific test IDs
    python scripts/convert_functional_cases_to_eval.py \
        --input ~/Work/okp-mcp/tests/functional_cases.py \
        --output config/okp_mcp_test_suites/subset.yaml \
        --filter "RSPEED_2482,RSPEED_2481"
"""

import argparse
import ast
import re
from pathlib import Path
from typing import Any

import yaml


def parse_functional_cases_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse functional_cases.py and extract test case data.

    Args:
        file_path: Path to functional_cases.py

    Returns:
        List of dicts with test case data:
        {
            'test_id': 'RSPEED_2482',
            'question': '...',
            'expected_doc_refs': [...],
            'required_facts': [...],
            'forbidden_claims': [...],
            'expected_first_doc': '...' or None
        }
    """
    content = file_path.read_text(encoding="utf-8")

    # Parse the Python file as AST
    tree = ast.parse(content)

    test_cases = []

    # Find FUNCTIONAL_TEST_CASES list
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "FUNCTIONAL_TEST_CASES":
                    # Found the list assignment
                    if isinstance(node.value, ast.List):
                        for element in node.value.elts:
                            case_data = _parse_pytest_param(element)
                            if case_data:
                                test_cases.append(case_data)

    return test_cases


def _parse_pytest_param(node: ast.expr) -> dict[str, Any] | None:
    """Parse a pytest.param(...) call into test case data.

    Args:
        node: AST node for pytest.param call

    Returns:
        Dict with test case data or None if not a valid pytest.param
    """
    if not isinstance(node, ast.Call):
        return None

    # Check if it's pytest.param(...)
    if isinstance(node.func, ast.Attribute):
        if node.func.attr != "param":
            return None
    else:
        return None

    # First positional arg should be FunctionalCase(...)
    if not node.args:
        return None

    functional_case = node.args[0]
    if not isinstance(functional_case, ast.Call):
        return None

    # Extract FunctionalCase fields
    case_data = {}
    for keyword in functional_case.keywords:
        field_name = keyword.arg
        field_value = _ast_to_python(keyword.value)
        case_data[field_name] = field_value

    # Extract test ID from id= keyword
    test_id = None
    for keyword in node.keywords:
        if keyword.arg == "id":
            test_id = _ast_to_python(keyword.value)

    if test_id:
        case_data["test_id"] = test_id

    return case_data


def _ast_to_python(node: ast.expr) -> Any:
    """Convert AST node to Python value.

    Args:
        node: AST expression node

    Returns:
        Python value (str, list, tuple, None, etc.)
    """
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Str):  # Python 3.7 compatibility
        return node.s
    elif isinstance(node, ast.List):
        return [_ast_to_python(elt) for elt in node.elts]
    elif isinstance(node, ast.Tuple):
        return tuple(_ast_to_python(elt) for elt in node.elts)
    elif isinstance(node, ast.NameConstant):  # Python 3.7 None/True/False
        return node.value
    else:
        # For complex expressions, try to eval (risky but functional_cases.py is trusted)
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError):
            return None


def convert_to_eval_yaml(
    test_cases: list[dict[str, Any]], filter_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Convert functional test cases to evaluation YAML format.

    Args:
        test_cases: List of parsed test case dicts
        filter_ids: Optional list of test IDs to include (e.g., ['RSPEED_2482'])

    Returns:
        List of evaluation data dicts in YAML format
    """
    eval_data = []

    for case in test_cases:
        test_id = case.get("test_id", "unknown")

        # Filter if requested
        if filter_ids and test_id not in filter_ids:
            continue

        # Convert expected_doc_refs to expected_urls
        # These are substrings that can match URLs or doc IDs
        doc_refs = case.get("expected_doc_refs", [])
        expected_urls = []
        for ref in doc_refs:
            # If it looks like a doc ID (just numbers), convert to URL pattern
            if ref.isdigit():
                expected_urls.append(f"access.redhat.com/solutions/{ref}")
            elif ref.startswith("http"):
                expected_urls.append(ref)
            else:
                # It's a substring pattern (like "rhel-container-compatibility")
                # Store as-is, will match in URL
                expected_urls.append(f"access.redhat.com/{ref}")

        # Convert required_facts to expected_keywords
        # Flatten tuples (OR alternatives) into individual keywords for now
        # TODO: Could enhance keywords_eval to support OR logic
        required_facts = case.get("required_facts", [])
        expected_keywords = []
        for fact in required_facts:
            if isinstance(fact, tuple):
                # For now, take the first alternative
                # Better: extend keywords_eval to support alternatives
                expected_keywords.append(fact[0])
            else:
                expected_keywords.append(fact)

        # Build turn data
        turn_data = {
            "turn_id": 1,
            "query": case.get("question", ""),
            "expected_urls": expected_urls,
            "expected_keywords": expected_keywords,
            "turn_metrics": [
                "custom:url_retrieval_eval",
                "custom:keywords_eval",
                "ragas:context_precision_without_reference",
                "ragas:context_relevance",
            ],
        }

        # Add forbidden_claims if present (we'll create this metric next)
        forbidden_claims = case.get("forbidden_claims", [])
        if forbidden_claims:
            turn_data["forbidden_claims"] = forbidden_claims
            turn_data["turn_metrics"].append("custom:forbidden_claims_eval")

        # Build conversation group
        eval_entry = {
            "conversation_group_id": test_id,
            "tag": "okp-mcp-functional",
            "turns": [turn_data],
        }

        eval_data.append(eval_entry)

    return eval_data


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert okp-mcp functional test cases to evaluation YAML"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to functional_cases.py (e.g., ~/Work/okp-mcp/tests/functional_cases.py)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output YAML file path (e.g., config/okp_mcp_test_suites/functional_tests.yaml)",
    )
    parser.add_argument(
        "--filter",
        help="Comma-separated list of test IDs to include (e.g., 'RSPEED_2482,RSPEED_2481')",
    )

    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return 1

    # Parse filter IDs
    filter_ids = None
    if args.filter:
        filter_ids = [tid.strip() for tid in args.filter.split(",")]
        print(f"📋 Filtering to test IDs: {filter_ids}")

    print(f"\n{'='*80}")
    print(f"Converting okp-mcp Functional Tests → Evaluation YAML")
    print(f"{'='*80}")
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"{'='*80}\n")

    # Parse functional_cases.py
    print("📖 Parsing functional_cases.py...")
    test_cases = parse_functional_cases_file(input_path)
    print(f"✅ Found {len(test_cases)} test cases")

    if not test_cases:
        print("❌ No test cases found in input file")
        return 1

    # Convert to evaluation format
    print("\n🔄 Converting to evaluation format...")
    eval_data = convert_to_eval_yaml(test_cases, filter_ids)
    print(f"✅ Converted {len(eval_data)} test cases")

    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write YAML
    print(f"\n💾 Writing to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            eval_data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )

    print(f"✅ Conversion complete!")
    print(f"\n{'='*80}")
    print(f"Next Steps:")
    print(f"{'='*80}")
    print(f"1. Review the generated YAML: {output_path}")
    print(f"2. Run evaluation suite:")
    print(
        f"   ./run_mcp_retrieval_suite.sh --config {output_path.relative_to(Path.cwd())}"
    )
    print(f"3. Analyze results with stability analysis:")
    print(
        f"   python scripts/analyze_url_retrieval_stability.py --input mcp_retrieval_output/suite_*/run_*/evaluation_*_detailed.csv"
    )
    print(f"{'='*80}\n")

    # Print summary
    print("📊 Conversion Summary:")
    print(f"  Test cases: {len(eval_data)}")
    print(f"  Tag: okp-mcp-functional")
    print(f"  Metrics per turn:")
    if eval_data:
        metrics = eval_data[0]["turns"][0]["turn_metrics"]
        for metric in metrics:
            print(f"    • {metric}")

    return 0


if __name__ == "__main__":
    exit(main())
