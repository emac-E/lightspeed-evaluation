#!/usr/bin/env python3
"""
Analyze tool calls to determine if OKP MCP was invoked.

This helps distinguish:
1. OKP tool called but returned empty (docs actually missing)
2. OKP tool not called at all (routing issue)
"""

import pandas as pd
import json
from pathlib import Path


def analyze_tool_calls(csv_path: Path, run_name: str = ""):
    """Analyze tool calls for questions with and without contexts."""

    # Load the CSV
    df = pd.read_csv(csv_path)

    # Get one row per conversation (take first metric for each conv)
    conv_df = df.drop_duplicates(subset=['conversation_group_id']).copy()

    # Check if contexts and tool_calls exist
    conv_df['has_context'] = conv_df['contexts'].notna() & (conv_df['contexts'] != '') & (conv_df['contexts'] != '[]')
    conv_df['has_tool_calls'] = conv_df['tool_calls'].notna() & (conv_df['tool_calls'] != '') & (conv_df['tool_calls'] != '[]')

    print("=" * 80)
    print(f"TOOL CALLS ANALYSIS {run_name}")
    print("=" * 80)

    print(f"\nTotal conversations: {len(conv_df)}")
    print(f"With contexts: {conv_df['has_context'].sum()}")
    print(f"With tool_calls logged: {conv_df['has_tool_calls'].sum()}")

    # Cross-tabulation
    print("\n" + "=" * 80)
    print("CONTEXTS vs TOOL_CALLS")
    print("=" * 80)

    ct = pd.crosstab(conv_df['has_context'], conv_df['has_tool_calls'],
                     rownames=['Has Context'], colnames=['Has Tool Calls'],
                     margins=True)
    print(ct)

    # Examine specific cases
    print("\n" + "=" * 80)
    print("CASES WITH NO CONTEXT - TOOL CALL CHECK")
    print("=" * 80)

    no_ctx = conv_df[~conv_df['has_context']]
    print(f"\nTotal questions with NO context: {len(no_ctx)}")

    for idx, row in no_ctx.iterrows():
        conv_id = row['conversation_group_id']
        q_num = conv_id.split('_q')[-1] if '_q' in conv_id else '?'

        print(f"\nQ{q_num} - {conv_id}:")
        print(f"  Query: {row['query'][:80]}...")

        tool_calls = row['tool_calls']
        if pd.isna(tool_calls) or tool_calls == '' or tool_calls == '[]':
            print(f"  Tool Calls: ❌ NO TOOL CALLS LOGGED")
            print(f"    → Possible routing issue or API answered without calling tools")
        else:
            # Parse tool calls (format: list of lists of dicts)
            try:
                tc_data = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
                if isinstance(tc_data, list):
                    # Flatten nested lists
                    all_tools = []
                    for item in tc_data:
                        if isinstance(item, list):
                            all_tools.extend(item)
                        else:
                            all_tools.append(item)

                    print(f"  Tool Calls: ✓ {len(all_tools)} tool(s) called")
                    for tc in all_tools:
                        if isinstance(tc, dict):
                            tool_name = tc.get('tool_name', tc.get('name', 'unknown'))
                            args = tc.get('arguments', {})
                            print(f"    - {tool_name}: {args}")
                        else:
                            print(f"    - {tc}")
                else:
                    print(f"  Tool Calls: {tc_data}")
            except Exception as e:
                print(f"  Tool Calls: ? Parse error: {e}")
                print(f"  Raw: {str(tool_calls)[:200]}")

    # Check if OKP tools were used at all
    print("\n" + "=" * 80)
    print("OKP TOOL USAGE")
    print("=" * 80)

    okp_usage = {'total_with_tools': 0, 'okp_tools_used': 0, 'tool_names': set()}

    for idx, row in conv_df[conv_df['has_tool_calls']].iterrows():
        tool_calls = row['tool_calls']
        try:
            tc_data = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
            if isinstance(tc_data, list):
                okp_usage['total_with_tools'] += 1
                # Flatten nested lists
                all_tools = []
                for item in tc_data:
                    if isinstance(item, list):
                        all_tools.extend(item)
                    else:
                        all_tools.append(item)

                for tc in all_tools:
                    if isinstance(tc, dict):
                        tool_name = tc.get('tool_name', tc.get('name', ''))
                        okp_usage['tool_names'].add(tool_name)
                        # Check if it's an OKP-related tool
                        args = tc.get('arguments', {})
                        server = args.get('server_label', '').lower()
                        if 'okp' in server or 'okp' in tool_name.lower() or 'search' in tool_name.lower() or 'portal' in tool_name.lower():
                            okp_usage['okp_tools_used'] += 1
                            break  # Count once per question
        except:
            pass

    print(f"\nQuestions with tool calls: {okp_usage['total_with_tools']}")
    print(f"Questions using OKP-like tools: {okp_usage['okp_tools_used']}")
    print(f"\nAll tool names found:")
    for tool in sorted(okp_usage['tool_names']):
        if tool:
            print(f"  - {tool}")

    return {
        'total': len(conv_df),
        'has_context': conv_df['has_context'].sum(),
        'has_tool_calls': conv_df['has_tool_calls'].sum(),
        'no_context_no_tools': len(conv_df[~conv_df['has_context'] & ~conv_df['has_tool_calls']]),
        'no_context_with_tools': len(conv_df[~conv_df['has_context'] & conv_df['has_tool_calls']]),
    }


def main():
    """Analyze tool calls across all runs."""
    current_dir = Path.cwd()
    if current_dir.name != 'generality':
        current_dir = Path(__file__).parent

    all_results = {}

    # Analyze each run
    for run_num in [1, 2, 3]:
        run_dir = current_dir / f"run{run_num}"
        csv_files = list(run_dir.glob("*_detailed.csv"))

        if csv_files:
            print(f"\n{'='*80}")
            print(f"RUN {run_num}")
            print(f"{'='*80}")
            results = analyze_tool_calls(csv_files[0], f"- Run {run_num}")
            all_results[f"run{run_num}"] = results

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY ACROSS ALL RUNS")
    print("=" * 80)

    total_no_ctx_no_tools = sum(r['no_context_no_tools'] for r in all_results.values())
    total_no_ctx_with_tools = sum(r['no_context_with_tools'] for r in all_results.values())

    print(f"\nNo context + No tool calls: {total_no_ctx_no_tools}")
    print(f"  → Likely: API answered directly without RAG (routing issue)")

    print(f"\nNo context + Tool calls logged: {total_no_ctx_with_tools}")
    print(f"  → Likely: Tool called but returned empty (docs actually missing)")

    print("\n" + "=" * 80)
    print("INTERPRETATION")
    print("=" * 80)
    print("\nIf 'No context + No tool calls':")
    print("  - The API/system decided not to use RAG at all")
    print("  - Could be intentional (simple question) or routing issue")
    print("\nIf 'No context + Tool calls logged':")
    print("  - The tool was called but returned no results")
    print("  - Documents are genuinely missing from OKP")


if __name__ == "__main__":
    main()
