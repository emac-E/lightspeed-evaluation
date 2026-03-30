#!/usr/bin/env python3
"""
Extract and display contexts for a specific question.
"""

import pandas as pd
import json
import sys

def extract_contexts(csv_file, conversation_id, turn_id='turn1'):
    """Extract contexts for a specific question."""
    df = pd.read_csv(csv_file)

    # Find rows for this conversation
    rows = df[
        (df['conversation_group_id'] == conversation_id) &
        (df['turn_id'] == turn_id)
    ]

    if len(rows) == 0:
        print(f"No data found for {conversation_id}/{turn_id}")
        return

    # Get first row (all rows should have same contexts)
    row = rows.iloc[0]

    print(f"Conversation: {conversation_id}")
    print(f"Turn: {turn_id}")
    print(f"Query: {row['query']}")
    print("")
    print("=" * 80)
    print("CONTEXTS RETRIEVED:")
    print("=" * 80)

    contexts_str = row['contexts']

    if pd.isna(contexts_str) or contexts_str == '' or contexts_str == 'null':
        print("No contexts retrieved!")
        return

    try:
        if contexts_str.startswith('['):
            contexts = json.loads(contexts_str)
        else:
            contexts = [contexts_str]

        print(f"\nTotal contexts: {len(contexts)}\n")

        for i, ctx in enumerate(contexts, 1):
            print(f"--- CONTEXT {i} ---")
            print(ctx[:500] if len(ctx) > 500 else ctx)
            if len(ctx) > 500:
                print(f"... ({len(ctx) - 500} more characters)")
            print("")

    except Exception as e:
        print(f"Error parsing contexts: {e}")
        print(f"Raw contexts string (first 1000 chars):")
        print(contexts_str[:1000])


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python extract_contexts_for_question.py <csv_file> <conversation_id> [turn_id]")
        sys.exit(1)

    csv_file = sys.argv[1]
    conversation_id = sys.argv[2]
    turn_id = sys.argv[3] if len(sys.argv) > 3 else 'turn1'

    extract_contexts(csv_file, conversation_id, turn_id)
