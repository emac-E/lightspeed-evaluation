#!/usr/bin/env python3
"""
Generate Jira issue proposals for RAG context retrieval failures.
"""

import pandas as pd
import json
import re
from pathlib import Path
import sys

def categorize_context(ctx_str):
    """Categorize a context to identify boilerplate."""
    ctx_str = str(ctx_str)

    # Check for common boilerplate patterns
    if '⚠️ WARNING: Some results indicate a feature was deprecated' in ctx_str:
        return 'System Warning (Deprecation Notice)'
    elif "['title', 'legalnotice']" in ctx_str or "'legalnotice'" in ctx_str:
        return 'Legal Notice / Boilerplate'
    elif ctx_str.strip().startswith('- name:') and 'hosts:' in ctx_str and 'tasks:' in ctx_str:
        return 'Ansible Playbook Snippet'
    elif 'Red Hat Lightspeed Information and Resources' in ctx_str:
        return 'Lightspeed Meta-Information'
    elif len(ctx_str.strip()) < 50:
        return 'Fragment / Short Text'
    else:
        return 'Content'


def extract_all_context_info(contexts_str):
    """Extract info from all contexts including boilerplate."""
    context_list = []

    if pd.isna(contexts_str) or contexts_str == '' or contexts_str == 'null':
        return context_list

    try:
        if contexts_str.startswith('['):
            contexts = json.loads(contexts_str)
        else:
            contexts = [contexts_str]

        for i, ctx in enumerate(contexts, 1):
            ctx_str = str(ctx)

            info = {
                'number': i,
                'category': categorize_context(ctx_str),
                'preview': ctx_str[:150]
            }

            # Extract structured fields
            url_match = re.search(r'URL:\s*(https?://[^\s\n]+)', ctx_str)
            type_match = re.search(r'Type:\s*([^\n]+)', ctx_str)
            title_match = re.search(r'\*\*([^\*]+)\*\*', ctx_str)

            if url_match:
                info['url'] = url_match.group(1).rstrip('.')
            if type_match:
                info['type'] = type_match.group(1).strip()
            if title_match:
                title = title_match.group(1).strip()
                if not title.startswith('[') and len(title) < 200:
                    info['title'] = title

            context_list.append(info)

    except Exception as e:
        pass

    return context_list


def load_failure_data(csv_files):
    """Load and analyze failure data to identify worst performers."""

    all_data = []
    for csv_file in csv_files:
        df = pd.read_csv(csv_file)
        all_data.append(df)

    combined_df = pd.concat(all_data, ignore_index=True)

    # Get context metrics
    context_metrics = combined_df[
        combined_df['metric_identifier'].isin([
            'ragas:context_precision_without_reference',
            'ragas:context_relevance'
        ])
    ].copy()

    # Get answer correctness
    answer_correctness = combined_df[
        combined_df['metric_identifier'] == 'custom:answer_correctness'
    ][['conversation_group_id', 'turn_id', 'score', 'result']].copy()

    # Identify failures
    failed = context_metrics[context_metrics['result'] == 'FAIL'].copy()

    # Group by conversation to find worst performers
    issues = []

    for conv_id in failed['conversation_group_id'].unique():
        conv_data = context_metrics[context_metrics['conversation_group_id'] == conv_id]

        # Get first row for details
        first_row = conv_data.iloc[0]

        # Get all metrics for this conversation
        metrics = {}
        for _, row in conv_data.iterrows():
            metrics[row['metric_identifier']] = {
                'score': row['score'],
                'result': row['result']
            }

        # Get answer correctness
        ac = answer_correctness[answer_correctness['conversation_group_id'] == conv_id]
        ac_score = ac['score'].iloc[0] if len(ac) > 0 else None
        ac_result = ac['result'].iloc[0] if len(ac) > 0 else None

        # Calculate severity
        avg_context_score = sum(m['score'] for m in metrics.values()) / len(metrics) if metrics else 0

        # High severity if answer is correct but contexts are bad (RAG bypass)
        is_rag_bypass = (ac_score is not None and ac_score >= 0.9 and avg_context_score < 0.3)

        # Parse ALL contexts
        contexts_str = first_row['contexts']
        all_contexts = extract_all_context_info(contexts_str)

        issues.append({
            'conv_id': conv_id,
            'turn_id': first_row['turn_id'],
            'query': first_row['query'],
            'expected': first_row['expected_response'],
            'response': first_row['response'],
            'contexts': contexts_str,
            'all_contexts': all_contexts,
            'metrics': metrics,
            'ac_score': ac_score,
            'ac_result': ac_result,
            'avg_context_score': avg_context_score,
            'is_rag_bypass': is_rag_bypass,
            'severity': 'Critical' if is_rag_bypass else 'High' if avg_context_score < 0.2 else 'Medium'
        })

    # Sort by severity
    severity_order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    issues.sort(key=lambda x: (severity_order[x['severity']], x['avg_context_score']))

    return issues


def generate_jira_issue_description(issue):
    """Generate detailed Jira issue description."""

    desc = []

    # Summary section
    desc.append("h2. Summary")
    desc.append("")
    desc.append(f"The query *\"{issue['query']}\"* is failing context retrieval metrics in the evaluation framework.")
    desc.append("")

    if issue['is_rag_bypass']:
        desc.append("{panel:bgColor=#FFEBE9}")
        desc.append("*RAG_BYPASS DETECTED*: The LLM answered correctly despite poor/no context retrieval, ")
        desc.append("indicating it used parametric knowledge instead of retrieved documentation.")
        desc.append("{panel}")
        desc.append("")

    # Metrics section
    desc.append("h2. Metrics")
    desc.append("")
    desc.append("||Metric||Score||Result||")

    for metric_name, metric_data in issue['metrics'].items():
        metric_short = metric_name.replace('ragas:', '').replace('_without_reference', '')
        emoji = "(x)" if metric_data['result'] == 'FAIL' else "(/) "
        desc.append(f"|{metric_short}|{metric_data['score']:.3f}|{metric_data['result']} {emoji}|")

    if issue['ac_score'] is not None:
        emoji = "(x)" if issue['ac_result'] == 'FAIL' else "(/) "
        desc.append(f"|answer_correctness|{issue['ac_score']:.3f}|{issue['ac_result']} {emoji}|")

    desc.append("")

    # Context Analysis
    desc.append("h2. Context Retrieval Analysis")
    desc.append("")
    desc.append(f"*Contexts Retrieved:* {len(issue['all_contexts'])}")
    desc.append("")

    if len(issue['all_contexts']) == 0:
        desc.append("{color:red}*No contexts were retrieved by okp-mcp!*{color}")
        desc.append("")
        desc.append("This indicates:")
        desc.append("* Query formulation issue - Solr query may not be matching relevant documents")
        desc.append("* Missing documentation - Content may not be indexed")
        desc.append("* Incorrect query parameters - Search may be too restrictive")
    elif len(issue['all_contexts']) > 50:
        desc.append("{color:orange}*Over-retrieval detected*{color}")
        desc.append("")
        desc.append(f"Retrieved {len(issue['all_contexts'])} contexts when optimal is 10-20.")
        desc.append("This causes:")
        desc.append("* High noise-to-signal ratio")
        desc.append("* LLM must dig through irrelevant content")
        desc.append("* Increased token costs")

    # Show ALL contexts categorized
    if issue['all_contexts']:
        desc.append("")
        desc.append("h3. All Retrieved Contexts (Categorized)")
        desc.append("")
        desc.append("The following shows ALL contexts retrieved, including boilerplate that should be filtered:")
        desc.append("")

        # Count categories
        category_counts = {}
        for ctx in issue['all_contexts']:
            cat = ctx['category']
            category_counts[cat] = category_counts.get(cat, 0) + 1

        desc.append("*Category Breakdown:*")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            desc.append(f"* {cat}: {count}")
        desc.append("")

        # List all contexts
        for ctx in issue['all_contexts']:
            num = ctx['number']
            cat = ctx['category']

            if ctx.get('url'):
                doc_type = ctx.get('type', 'Unknown')
                title = ctx.get('title', '')
                if title:
                    desc.append(f"{num}. *[{cat}]* {doc_type}: {title}")
                    desc.append(f"   {ctx['url']}")
                else:
                    desc.append(f"{num}. *[{cat}]* {doc_type}: {ctx['url']}")
            else:
                # Show boilerplate preview
                preview = ctx['preview']
                desc.append(f"{num}. *[{cat}]* {{color:grey}}{preview}...{{color}}")

            desc.append("")

    # Root Cause Analysis
    desc.append("h2. Root Cause Analysis")
    desc.append("")

    precision_score = issue['metrics'].get('ragas:context_precision_without_reference', {}).get('score', 1.0)
    relevance_score = issue['metrics'].get('ragas:context_relevance', {}).get('score', 1.0)

    causes = []

    # Boilerplate analysis
    if issue['all_contexts']:
        boilerplate_count = sum(1 for ctx in issue['all_contexts']
                               if ctx['category'] in ['Legal Notice / Boilerplate',
                                                     'System Warning (Deprecation Notice)',
                                                     'Lightspeed Meta-Information'])
        if boilerplate_count > 0:
            pct = (boilerplate_count / len(issue['all_contexts']) * 100)
            causes.append(f"*Boilerplate pollution*: {boilerplate_count}/{len(issue['all_contexts'])} ({pct:.0f}%) contexts are boilerplate")
            causes.append("** Legal notices, warnings, meta-information waste context window")
            causes.append("** Need to filter: legal notices, deprecation warnings, Lightspeed meta-docs")

    if len(issue['all_contexts']) == 0:
        causes.append("*No retrieval*: okp-mcp query returned zero results")
        causes.append("** Check if documentation exists for this topic")
        causes.append("** Verify Solr indexing")
        causes.append("** Review query formulation")

    if precision_score < 0.3 and len(issue['all_contexts']) > 0:
        causes.append("*Low precision*: Most retrieved contexts are not relevant")
        causes.append("** Ranking/scoring algorithm prioritizing wrong documents")
        causes.append("** Boilerplate/metadata outranking actual content")

    if relevance_score < 0.3 and len(issue['all_contexts']) > 0:
        causes.append("*Low relevance*: Retrieved docs don't contain needed information")
        causes.append("** Semantic search not understanding query intent")
        causes.append("** Missing key documentation sections")

    if len(issue['all_contexts']) > 50:
        causes.append("*Over-retrieval*: Returning too many results")
        causes.append("** Missing result count limit in Solr query")
        causes.append("** Should implement {{rows=10}} or {{rows=20}}")

    for cause in causes:
        desc.append(f"* {cause}")

    desc.append("")

    # Expected Response
    if issue['expected']:
        desc.append("h2. Expected Correct Answer")
        desc.append("")
        desc.append("{code}")
        desc.append(str(issue['expected'])[:500])
        if len(str(issue['expected'])) > 500:
            desc.append("...")
        desc.append("{code}")
        desc.append("")

    # Recommendations
    desc.append("h2. Recommended Fixes")
    desc.append("")

    fixes = []

    # Boilerplate filtering recommendations
    if issue['all_contexts']:
        boilerplate_count = sum(1 for ctx in issue['all_contexts']
                               if ctx['category'] in ['Legal Notice / Boilerplate',
                                                     'System Warning (Deprecation Notice)',
                                                     'Lightspeed Meta-Information'])
        if boilerplate_count > 0:
            fixes.append("*Boilerplate Filtering:*")
            fixes.append("1. Filter out legal notices: {{fq=-content_type:legalnotice}}")
            fixes.append("2. Exclude system warnings and meta-information")
            fixes.append("3. Boost actual content over metadata: {{qf='content^5.0 title^2.0'}}")

    if len(issue['all_contexts']) == 0:
        fixes.append("*Missing Documentation:*")
        fixes.append("1. Verify documentation exists and is indexed in Solr")
        fixes.append("2. Review query formulation - may need to expand search terms")
        fixes.append("3. Check for indexing issues with this content type")

    if len(issue['all_contexts']) > 50:
        fixes.append("*Result Limiting:*")
        fixes.append("1. Implement result limit: {{rows=10}} in Solr query")
        fixes.append("2. Improve ranking to surface best results first")

    if precision_score < 0.3:
        fixes.append("*Ranking Improvements:*")
        fixes.append("1. Boost content fields over metadata")
        fixes.append("2. Adjust BM25 scoring parameters")
        fixes.append("3. De-prioritize broad/generic documentation")

    if relevance_score < 0.3:
        fixes.append("*Semantic Search:*")
        fixes.append("1. Review semantic search configuration")
        fixes.append("2. Add synonym expansion for technical terms")
        fixes.append("3. Verify documentation completeness")

    for fix in fixes:
        desc.append(f"* {fix}")

    desc.append("")

    # Testing section
    desc.append("h2. Acceptance Criteria")
    desc.append("")
    desc.append("- Context precision score improves to >0.7")
    desc.append("- Context relevance score improves to >0.7")
    desc.append("- Number of retrieved contexts is between 10-20")
    desc.append("- Retrieved contexts contain relevant information for the query")
    desc.append("- Boilerplate/legal notices are filtered out")
    desc.append("")

    # Reference
    desc.append("h2. Test Case Reference")
    desc.append("")
    desc.append(f"*Conversation ID:* {issue['conv_id']}")
    desc.append(f"*Turn ID:* {issue['turn_id']}")
    desc.append("")
    desc.append("Run evaluation to verify fix:")
    desc.append("{code:bash}")
    desc.append("lightspeed-eval \\")
    desc.append("  --system-config config/system.yaml \\")
    desc.append("  --eval-data config/<test_file>.yaml \\")
    desc.append("  --output-dir eval_output/verification/")
    desc.append("{code}")

    return '\n'.join(desc)


def generate_jira_issue_proposals(issues, limit=None):
    """Generate Jira issue proposals."""

    proposals = []

    issues_to_process = issues[:limit] if limit else issues

    for issue in issues_to_process:
        summary = f"okp-mcp: Poor context retrieval for \"{issue['query'][:80]}{'...' if len(issue['query']) > 80 else ''}\""

        description = generate_jira_issue_description(issue)

        # Determine labels
        labels = ["rag-quality", "context-retrieval", "okp-mcp"]
        if issue['is_rag_bypass']:
            labels.append("rag-bypass")
        if len(issue['all_contexts']) == 0:
            labels.append("zero-retrieval")
        if len(issue['all_contexts']) > 50:
            labels.append("over-retrieval")

        # Check for boilerplate
        if issue['all_contexts']:
            boilerplate_count = sum(1 for ctx in issue['all_contexts']
                                   if ctx['category'] in ['Legal Notice / Boilerplate',
                                                         'System Warning (Deprecation Notice)',
                                                         'Lightspeed Meta-Information'])
            if boilerplate_count > len(issue['all_contexts']) * 0.2:  # >20% boilerplate
                labels.append("boilerplate-pollution")

        proposals.append({
            'summary': summary,
            'description': description,
            'issue_type': 'Bug',
            'priority': 'High' if issue['severity'] in ['Critical', 'High'] else 'Medium',
            'labels': labels,
            'severity': issue['severity'],
            'conv_id': issue['conv_id'],
            'components': ['okp-mcp']  # Assuming this component exists
        })

    return proposals


if __name__ == '__main__':
    # Find all detailed CSV files
    base_dir = Path('/home/emackey/Work/lightspeed-core/lightspeed-evaluation/eval_output/full_suite_20260323_152904')

    csv_files = list(base_dir.glob('*/evaluation_*_detailed.csv'))

    if not csv_files:
        print("No CSV files found!")
        sys.exit(1)

    print(f"Analyzing {len(csv_files)} CSV files...")

    # Load and analyze
    issues = load_failure_data(csv_files)

    # Generate proposals for worst performers (top 10)
    proposals = generate_jira_issue_proposals(issues, limit=10)

    # Save to file for review
    output_file = base_dir / 'JIRA_ISSUE_PROPOSALS.json'
    with open(output_file, 'w') as f:
        json.dump(proposals, f, indent=2)

    # Also create human-readable version
    readable_file = base_dir / 'JIRA_ISSUE_PROPOSALS.md'
    with open(readable_file, 'w') as f:
        f.write("# Jira Issue Proposals for RAG Context Retrieval Failures\n\n")
        f.write(f"**Total Issues to Create:** {len(proposals)}\n\n")
        f.write(f"**Severity Breakdown:**\n")

        severity_counts = {}
        for p in proposals:
            severity_counts[p['severity']] = severity_counts.get(p['severity'], 0) + 1

        for severity, count in sorted(severity_counts.items()):
            f.write(f"- {severity}: {count}\n")

        f.write("\n---\n\n")

        for i, proposal in enumerate(proposals, 1):
            f.write(f"## Issue {i}: {proposal['conv_id']}\n\n")
            f.write(f"**Summary:** {proposal['summary']}\n\n")
            f.write(f"**Priority:** {proposal['priority']}\n\n")
            f.write(f"**Severity:** {proposal['severity']}\n\n")
            f.write(f"**Labels:** {', '.join(proposal['labels'])}\n\n")
            f.write("**Description:**\n\n")
            # Convert Jira markup to Markdown for readability
            desc = proposal['description']
            desc = desc.replace('h2. ', '### ')
            desc = desc.replace('h3. ', '#### ')
            desc = desc.replace('{panel:bgColor=#FFEBE9}', '> **WARNING**\n> ')
            desc = desc.replace('{panel}', '')
            desc = desc.replace('{color:red}', '**')
            desc = desc.replace('{color:orange}', '**')
            desc = desc.replace('{color:grey}', '*')
            desc = desc.replace('{color}', '**')
            desc = desc.replace('{quote}', '```')
            desc = desc.replace('{code}', '```')
            desc = desc.replace('{code:bash}', '```bash')
            desc = desc.replace('||', '|')
            desc = desc.replace('(x)', '❌')
            desc = desc.replace('(/) ', '✅')
            f.write(desc)
            f.write("\n\n---\n\n")

    print(f"\n{'='*80}")
    print(f"Jira Issue Proposals Generated")
    print(f"{'='*80}")
    print(f"\nTotal issues analyzed: {len(issues)}")
    print(f"Proposals generated: {len(proposals)}")
    print(f"\nFiles created:")
    print(f"  - {output_file} (JSON for automation)")
    print(f"  - {readable_file} (Human-readable)")
    print(f"\nSeverity breakdown:")
    for severity, count in sorted(severity_counts.items()):
        print(f"  {severity}: {count}")
    print(f"\nReview the proposals in: {readable_file}")
    print(f"\nNext steps:")
    print(f"  1. Review and edit proposals")
    print(f"  2. Approve which issues to create")
    print(f"  3. I will then create approved issues in Jira")
