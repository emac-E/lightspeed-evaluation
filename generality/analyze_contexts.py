#!/usr/bin/env python3
"""
Analyze whether contexts are being returned from OKP MCP.

If contexts are empty/missing, it suggests either:
1. OKP MCP is not being called
2. OKP database doesn't have relevant documents
3. Query routing/retrieval is failing
"""

import pandas as pd
import json
from pathlib import Path


def analyze_contexts(csv_path: Path, run_name: str = ""):
    """Analyze contexts in evaluation results."""

    # Load the CSV
    df = pd.read_csv(csv_path)

    # Filter for answer_correctness metric
    ac_df = df[df['metric_identifier'] == 'custom:answer_correctness'].copy()

    # Check if contexts is null/empty
    ac_df['has_context'] = ac_df['contexts'].notna() & (ac_df['contexts'] != '') & (ac_df['contexts'] != '[]')

    print("=" * 80)
    print(f"CONTEXTS ANALYSIS {run_name}")
    print("=" * 80)

    print(f"\nTotal answer_correctness evaluations: {len(ac_df)}")
    print(f"With contexts: {ac_df['has_context'].sum()}")
    print(f"Without contexts: {(~ac_df['has_context']).sum()}")

    # Break down by pass/fail
    print("\n" + "=" * 80)
    print("CONTEXTS BY RESULT")
    print("=" * 80)

    results_summary = {}
    for result in ['PASS', 'FAIL']:
        subset = ac_df[ac_df['result'] == result]
        with_ctx = subset['has_context'].sum()
        total = len(subset)

        results_summary[result] = {
            'total': total,
            'with_contexts': with_ctx,
            'without_contexts': total - with_ctx,
        }

        print(f"\n{result}:")
        print(f"  Total: {total}")
        print(f"  With contexts: {with_ctx} ({100*with_ctx/total:.1f}%)")
        print(f"  Without contexts: {total - with_ctx} ({100*(total-with_ctx)/total:.1f}%)")

    # Show sample contexts for failed questions
    print("\n" + "=" * 80)
    print("SAMPLE FAILED QUESTIONS - CONTEXT CHECK")
    print("=" * 80)

    failed = ac_df[ac_df['result'] == 'FAIL']
    for idx, row in failed.head(5).iterrows():
        conv_id = row['conversation_group_id']
        # Extract question number
        q_num = conv_id.split('_q')[-1] if '_q' in conv_id else '?'

        print(f"\nQ{q_num} - {conv_id} (FAIL):")
        print(f"  Query: {row['query'][:100]}{'...' if len(row['query']) > 100 else ''}")

        ctx = row['contexts']
        if pd.isna(ctx) or ctx == '' or ctx == '[]':
            print(f"  Contexts: ❌ EMPTY/NULL - No docs retrieved!")
        else:
            # Try to parse as JSON to see structure
            try:
                ctx_data = json.loads(ctx) if isinstance(ctx, str) else ctx
                if isinstance(ctx_data, list):
                    print(f"  Contexts: ✓ {len(ctx_data)} documents retrieved")
                    if ctx_data:
                        # Show first doc preview
                        first_doc = str(ctx_data[0])[:200]
                        print(f"  Preview: {first_doc}...")
                else:
                    print(f"  Contexts: ? Unexpected type: {type(ctx_data)}")
            except Exception as e:
                print(f"  Contexts: ? Parse error: {e}")
                print(f"  Raw: {str(ctx)[:100]}...")

    return results_summary


def main():
    """Analyze contexts across all runs."""
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
            results = analyze_contexts(csv_files[0], f"- Run {run_num}")
            all_results[f"run{run_num}"] = results

    # Summary across all runs
    print("\n" + "=" * 80)
    print("SUMMARY ACROSS ALL RUNS")
    print("=" * 80)

    total_fails = sum(r['FAIL']['total'] for r in all_results.values())
    total_fails_no_ctx = sum(r['FAIL']['without_contexts'] for r in all_results.values())

    total_pass = sum(r['PASS']['total'] for r in all_results.values())
    total_pass_no_ctx = sum(r['PASS']['without_contexts'] for r in all_results.values())

    print(f"\nFAILED questions:")
    print(f"  Total: {total_fails}")
    print(f"  Without contexts: {total_fails_no_ctx} ({100*total_fails_no_ctx/total_fails:.1f}%)")

    print(f"\nPASSED questions:")
    print(f"  Total: {total_pass}")
    print(f"  Without contexts: {total_pass_no_ctx} ({100*total_pass_no_ctx/total_pass:.1f}%)")

    print("\n" + "=" * 80)
    print("CONCLUSIONS")
    print("=" * 80)

    print(f"\n📊 RAG_BYPASS Analysis:")
    print(f"   PASSED without context (successful RAG_BYPASS): {total_pass_no_ctx}/{total_pass} ({100*total_pass_no_ctx/total_pass:.1f}%)")
    print(f"   - Model used parametric knowledge successfully")

    print(f"\n   FAILED without context (missing docs): {total_fails_no_ctx}/{total_fails} ({100*total_fails_no_ctx/total_fails:.1f}%)")
    print(f"   - OKP retrieval failed, AND parametric knowledge insufficient")

    if total_fails_no_ctx > 0:
        print("\n⚠️  Failed questions with NO contexts suggest:")
        print("   - Documents don't exist in OKP Solr database")
        print("   - Query routing/retrieval is failing")
        print("   - Misspellings preventing successful search")

    fails_with_ctx = total_fails - total_fails_no_ctx
    if fails_with_ctx > 0:
        print(f"\n⚠️  Failed questions WITH contexts ({fails_with_ctx}/{total_fails}, {100*fails_with_ctx/total_fails:.1f}%):")
        print("   Issue is likely:")
        print("   - Context quality/relevance (wrong docs retrieved)")
        print("   - LLM answer generation from provided context")
        print("   - Ground truth mismatch")

    # Save results (convert int64 to int for JSON serialization)
    output_file = current_dir / "context_analysis.json"
    serializable_results = {}
    for run, data in all_results.items():
        serializable_results[run] = {}
        for result, stats in data.items():
            serializable_results[run][result] = {k: int(v) for k, v in stats.items()}

    with open(output_file, 'w') as f:
        json.dump(serializable_results, f, indent=2)

    print(f"\n✓ Detailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
