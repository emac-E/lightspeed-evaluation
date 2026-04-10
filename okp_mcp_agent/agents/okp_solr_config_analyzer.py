#!/usr/bin/env python3
"""Solr configuration analyzer and explain output parser.

Helps diagnose why Solr is ranking documents incorrectly by:
1. Parsing current Solr config from okp-mcp/src/okp_mcp/solr.py
2. Fetching Solr explain output to see scoring details
3. Analyzing which parameters might need tuning
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import requests


class SolrConfigAnalyzer:
    """Analyze Solr configuration and ranking decisions."""

    def __init__(self, okp_mcp_root: Path, solr_url: str = "http://localhost:8983/solr/portal"):
        """Initialize analyzer.

        Args:
            okp_mcp_root: Path to okp-mcp repository
            solr_url: Base URL for Solr portal core
        """
        self.okp_mcp_root = okp_mcp_root
        self.solr_url = solr_url.rstrip("/")
        self.select_url = f"{self.solr_url}/select"
        self.solr_py = okp_mcp_root / "src/okp_mcp/solr.py"

    def parse_current_config(self) -> Dict:
        """Parse current Solr configuration from solr.py.

        Returns:
            Dictionary with all edismax parameters and boost keywords
        """
        if not self.solr_py.exists():
            return {}

        content = self.solr_py.read_text()

        # Extract base_params dictionary (lines 95-151)
        params_match = re.search(r'base_params = \{(.*?)\}', content, re.DOTALL)
        if not params_match:
            return {}

        params_text = params_match.group(1)

        # Parse key parameters
        config = {}

        # Query fields with boosts
        qf_match = re.search(r'"qf":\s*"([^"]+)"', params_text)
        if qf_match:
            config["qf"] = qf_match.group(1)

        # Phrase boosts
        pf_match = re.search(r'"pf":\s*"([^"]+)"', params_text)
        if pf_match:
            config["pf"] = pf_match.group(1)

        pf2_match = re.search(r'"pf2":\s*"([^"]+)"', params_text)
        if pf2_match:
            config["pf2"] = pf2_match.group(1)

        pf3_match = re.search(r'"pf3":\s*"([^"]+)"', params_text)
        if pf3_match:
            config["pf3"] = pf3_match.group(1)

        # Phrase slop
        for param in ["ps", "ps2", "ps3"]:
            match = re.search(rf'"{param}":\s*"(\d+)"', params_text)
            if match:
                config[param] = match.group(1)

        # Minimum match
        mm_match = re.search(r'"mm":\s*"([^"]+)"', params_text)
        if mm_match:
            config["mm"] = mm_match.group(1)

        # Highlighting parameters
        # BM25 scoring for snippet selection
        for param in ["hl.score.k1", "hl.score.b", "hl.score.pivot"]:
            match = re.search(rf'"{param}":\s*"([^"]+)"', params_text)
            if match:
                config[param] = match.group(1)

        # Highlighting configuration
        for param in ["hl.snippets", "hl.fragsize"]:
            match = re.search(rf'"{param}":\s*"([^"]+)"', params_text)
            if match:
                config[param] = match.group(1)

        # Extract boost keywords (lines 248-269)
        boost_match = re.search(
            r'_EXTRACTION_BOOST_KEYWORDS = frozenset\(\s*\[(.*?)\]',
            content,
            re.DOTALL
        )
        if boost_match:
            keywords_text = boost_match.group(1)
            keywords = re.findall(r'"([^"]+)"', keywords_text)
            config["boost_keywords"] = keywords

        # Extract demote keywords (lines 271-278)
        demote_match = re.search(
            r'_EXTRACTION_DEMOTE_RHV = frozenset\(\s*\[(.*?)\]',
            content,
            re.DOTALL
        )
        if demote_match:
            keywords_text = demote_match.group(1)
            keywords = re.findall(r'"([^"]+)"', keywords_text)
            config["demote_keywords"] = keywords

        # Extract boost/demote multipliers (lines 308-313)
        boost_mult_match = re.search(r'multiplier \*= ([\d.]+)\s*# boost', content)
        if boost_mult_match:
            config["boost_multiplier"] = float(boost_mult_match.group(1))

        demote_mult_match = re.search(r'multiplier \*= ([\d.]+)\s*# demote', content)
        if demote_mult_match:
            config["demote_multiplier"] = float(demote_mult_match.group(1))

        return config

    def get_explain_output(
        self,
        query: str,
        doc_ids: Optional[List[str]] = None,
        num_docs: int = 10
    ) -> Dict:
        """Get Solr explain output showing why docs ranked the way they did.

        Args:
            query: User query text
            doc_ids: Optional list of specific doc IDs to explain
            num_docs: Number of top results to explain

        Returns:
            Dictionary with explain output and ranking details
        """
        params = {
            "q": query,
            "rows": num_docs,
            "wt": "json",
            "debugQuery": "on",  # Get explain output
            "fl": "id,title,url,score",
        }

        try:
            response = requests.get(self.select_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            result = {
                "query": query,
                "num_found": data["response"]["numFound"],
                "docs": data["response"]["docs"],
                "explain": {},
            }

            # Parse explain output (shows scoring formula for each doc)
            if "debug" in data and "explain" in data["debug"]:
                result["explain"] = data["debug"]["explain"]

            # If specific doc IDs requested, highlight them
            if doc_ids:
                result["requested_docs"] = {}
                for doc_id in doc_ids:
                    # Check if this doc appeared in results
                    found = next((d for d in result["docs"] if d["id"] == doc_id), None)
                    if found:
                        result["requested_docs"][doc_id] = {
                            "rank": result["docs"].index(found) + 1,
                            "score": found["score"],
                            "explain": result["explain"].get(doc_id, ""),
                        }
                    else:
                        # Doc didn't appear in top N - need to query for it specifically
                        result["requested_docs"][doc_id] = {
                            "rank": f">{num_docs}",
                            "score": None,
                            "explain": "Not in top results",
                        }

            return result

        except requests.RequestException as e:
            return {
                "query": query,
                "error": str(e),
            }

    def analyze_ranking_problems(
        self,
        query: str,
        expected_urls: List[str],
        retrieved_urls: List[str]
    ) -> Dict:
        """Analyze why expected docs didn't rank well.

        Args:
            query: User query
            expected_urls: URLs that should have been retrieved
            retrieved_urls: URLs that were actually retrieved

        Returns:
            Analysis with suggestions for config changes
        """
        # Extract doc IDs from URLs
        expected_ids = [self._url_to_doc_id(url) for url in expected_urls]
        retrieved_ids = [self._url_to_doc_id(url) for url in retrieved_urls]

        # Get explain output
        explain_data = self.get_explain_output(query, doc_ids=expected_ids, num_docs=20)

        # Analyze
        analysis = {
            "query": query,
            "expected_count": len(expected_urls),
            "retrieved_count": len(retrieved_urls),
            "missing_docs": [],
            "ranking_issues": [],
            "suggestions": [],
        }

        # Find missing expected docs
        for exp_id, exp_url in zip(expected_ids, expected_urls):
            if exp_id not in retrieved_ids[:10]:  # Not in top 10
                doc_info = explain_data.get("requested_docs", {}).get(exp_id, {})
                analysis["missing_docs"].append({
                    "url": exp_url,
                    "doc_id": exp_id,
                    "rank": doc_info.get("rank", "not found"),
                    "score": doc_info.get("score"),
                })

        # Generate suggestions based on patterns
        if len(analysis["missing_docs"]) > 0:
            analysis["suggestions"].append(
                "Expected documents are missing from top results. "
                "Consider: increasing field weights (qf), phrase boost (pf), "
                "or loosening minimum match (mm)."
            )

        return analysis

    def _url_to_doc_id(self, url: str) -> str:
        """Extract Solr document ID from URL.

        This is a heuristic - actual doc IDs may differ.
        """
        # Remove protocol and domain
        url = url.replace("https://", "").replace("http://", "")
        url = url.replace("access.redhat.com/", "")

        # Extract meaningful part
        match = re.match(r"(?:solutions|articles)/(\S+)", url)
        if match:
            return match.group(1)

        return url.rstrip("/")

    def format_config_summary(self) -> str:
        """Format current Solr config as human-readable summary.

        Returns:
            Multi-line string describing current configuration
        """
        config = self.parse_current_config()
        if not config:
            return "Could not parse Solr config"

        lines = [
            "=== CURRENT SOLR CONFIGURATION ===",
            "",
            "QUERY FIELD WEIGHTS (qf):",
            f"  {config.get('qf', 'Not found')}",
            "",
            "PHRASE BOOSTING:",
            f"  pf  (exact phrase):  {config.get('pf', 'Not found')}",
            f"  pf2 (bigrams):       {config.get('pf2', 'Not found')}",
            f"  pf3 (trigrams):      {config.get('pf3', 'Not found')}",
            "",
            "PHRASE SLOP:",
            f"  ps  (exact): {config.get('ps', 'Not found')} positions",
            f"  ps2 (bigrams): {config.get('ps2', 'Not found')} positions",
            f"  ps3 (trigrams): {config.get('ps3', 'Not found')} positions",
            "",
            "MINIMUM MATCH (mm):",
            f"  {config.get('mm', 'Not found')}",
            "  Explanation: For 1-2 terms all must match (-1 = all)",
            "               For 5+ terms, at least 75% must match",
            "",
            "BM25 HIGHLIGHTING PARAMS:",
            f"  k1 (term saturation): {config.get('hl.score.k1', 'Not found')}",
            f"  b (length norm):      {config.get('hl.score.b', 'Not found')}",
            f"  pivot (avg length):   {config.get('hl.score.pivot', 'Not found')} chars",
            "",
            "RE-RANKING MULTIPLIERS:",
            f"  Boost multiplier:  {config.get('boost_multiplier', 2.0)}x",
            f"  Demote multiplier: {config.get('demote_multiplier', 0.05)}x",
            "",
            f"BOOST KEYWORDS ({len(config.get('boost_keywords', []))} total):",
        ]

        for kw in config.get("boost_keywords", [])[:10]:
            lines.append(f"  - {kw}")
        if len(config.get("boost_keywords", [])) > 10:
            lines.append(f"  ... and {len(config['boost_keywords']) - 10} more")

        lines.extend([
            "",
            f"DEMOTE KEYWORDS ({len(config.get('demote_keywords', []))} total):",
        ])
        for kw in config.get("demote_keywords", []):
            lines.append(f"  - {kw}")

        return "\n".join(lines)

    def search_for_answer_content(
        self,
        keywords: List[str],
        expected_response: Optional[str] = None,
        num_results: int = 10
    ) -> List[Dict]:
        """Search Solr for documents that might contain the answer.

        Args:
            keywords: List of important keywords/phrases to search for
            expected_response: Full expected response text (will extract key phrases)
            num_results: Maximum number of results to return

        Returns:
            List of dicts with url, title, score, snippet
        """
        # Build search query from keywords and expected response
        search_terms = list(keywords)

        # Extract important phrases from expected_response if provided
        if expected_response:
            # Extract quoted phrases and capitalized terms (likely important concepts)
            import re
            # Find quoted text
            quoted = re.findall(r'"([^"]+)"', expected_response)
            search_terms.extend(quoted)

            # Find important capitalized phrases (like "Extended Life Support")
            # But skip sentence-initial caps
            words = expected_response.split()
            i = 0
            while i < len(words):
                # Skip first word of sentence
                if i == 0 or words[i-1].endswith(('.', '!', '?', ':')):
                    i += 1
                    continue
                # Check if this word starts a capitalized phrase
                if words[i][0].isupper():
                    phrase_words = [words[i]]
                    j = i + 1
                    # Collect consecutive capitalized words
                    while j < len(words) and words[j][0].isupper():
                        phrase_words.append(words[j])
                        j += 1
                    if len(phrase_words) > 1:  # Only multi-word phrases
                        search_terms.append(' '.join(phrase_words))
                        i = j
                    else:
                        i += 1
                else:
                    i += 1

        # Remove duplicates and empty strings
        search_terms = [t.strip() for t in search_terms if t.strip()]
        search_terms = list(dict.fromkeys(search_terms))  # Preserve order, remove dupes

        # Build Solr query - search in title, abstract, body
        # Use OR between terms to maximize recall
        query_parts = []
        for term in search_terms[:20]:  # Limit to top 20 terms
            # Escape special Solr characters
            escaped_term = term.replace('"', '\\"')
            # Search in multiple fields
            query_parts.append(f'(allTitle:"{escaped_term}" OR abstract:"{escaped_term}" OR body:"{escaped_term}")')

        if not query_parts:
            return []

        q = ' OR '.join(query_parts)

        # Query Solr
        try:
            params = {
                'q': q,
                'rows': num_results,
                'fl': 'id,view_uri,allTitle,abstract,score',
                'defType': 'edismax',
            }

            resp = requests.get(self.select_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            docs = data.get('response', {}).get('docs', [])
            results = []

            for doc in docs:
                # Build URL from view_uri or id (same as okp-mcp portal.py)
                uri = doc.get('view_uri') or doc.get('id', '')
                uri = uri.removesuffix('/index.html')
                url = f"https://access.redhat.com{uri}" if uri and not uri.startswith('http') else uri

                # Extract snippet from abstract or first part of body
                snippet = doc.get('abstract', [''])[0] if isinstance(doc.get('abstract'), list) else doc.get('abstract', '')
                if not snippet:
                    snippet = doc.get('body', [''])[0][:200] if isinstance(doc.get('body'), list) else doc.get('body', '')[:200]

                results.append({
                    'url': url,
                    'title': doc.get('allTitle', ['No title'])[0] if isinstance(doc.get('allTitle'), list) else doc.get('allTitle', 'No title'),
                    'score': doc.get('score', 0.0),
                    'snippet': snippet,
                    'doc_id': doc.get('id', ''),
                })

            return results

        except requests.RequestException as e:
            print(f"⚠️  Solr search failed: {e}")
            return []


if __name__ == "__main__":
    # Quick test
    from pathlib import Path

    okp_mcp_root = Path.home() / "Work/okp-mcp"
    analyzer = SolrConfigAnalyzer(okp_mcp_root)

    print(analyzer.format_config_summary())
    print("\n" + "=" * 80 + "\n")

    # Test explain output
    query = "Can I run a RHEL 6 container on RHEL 9?"
    print(f"Getting explain output for: {query}\n")

    explain = analyzer.get_explain_output(query, num_docs=3)

    if "error" in explain:
        print(f"❌ Solr query failed: {explain['error']}")
        print("   (This is expected if Solr is not running)")
    else:
        print(f"Found {explain['num_found']} results")
        print("\nTop 3 docs:")
        for i, doc in enumerate(explain.get("docs", []), 1):
            print(f"\n{i}. {doc.get('title', 'No title')}")
            print(f"   URL: {doc.get('url', 'No URL')}")
            print(f"   Score: {doc.get('score', 0):.2f}")
            print(f"   Explain: {explain.get('explain', {}).get(doc.get('id', ''), '')[:200]}...")
