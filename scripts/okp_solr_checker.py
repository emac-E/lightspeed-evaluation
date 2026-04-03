#!/usr/bin/env python3
"""Solr document checker for okp-mcp diagnostics.

Validates that expected documents exist in the Solr index and helps
identify missing documents or suggest URLs for test configs.
"""

import json
import re
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests


class SolrDocumentChecker:
    """Check if documents exist in okp-mcp Solr index."""

    def __init__(self, solr_url: str = "http://localhost:8983/solr/portal"):
        """Initialize Solr checker.

        Args:
            solr_url: Base URL for Solr portal core (default: http://localhost:8983/solr/portal)
        """
        self.solr_url = solr_url.rstrip("/")
        self.select_url = f"{self.solr_url}/select"

    def is_available(self) -> bool:
        """Check if Solr is accessible.

        Returns:
            True if Solr responds, False otherwise
        """
        try:
            response = requests.get(f"{self.solr_url}/admin/ping", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def extract_doc_id_from_url(self, url: str) -> Optional[str]:
        """Extract document ID from access.redhat.com URL.

        Examples:
            access.redhat.com/solutions/2726611 → 2726611
            access.redhat.com/articles/rhel9-eus-faq → rhel9-eus-faq
            access.redhat.com/rhel-container-compatibility → rhel-container-compatibility

        Args:
            url: access.redhat.com URL

        Returns:
            Document ID or None if not extractable
        """
        # Remove protocol if present
        url = url.replace("https://", "").replace("http://", "")

        # Remove access.redhat.com prefix
        if url.startswith("access.redhat.com/"):
            url = url.replace("access.redhat.com/", "")

        # Extract meaningful part
        # For solutions/articles, get the number/slug
        match = re.match(r"(?:solutions|articles)/(\S+)", url)
        if match:
            return match.group(1)

        # For other docs, return the slug
        # Remove trailing slashes
        url = url.rstrip("/")
        if url:
            return url

        return None

    def check_document_exists(self, url: str) -> Dict:
        """Check if a document exists in Solr by URL.

        Args:
            url: Expected URL (e.g., "access.redhat.com/solutions/2726611")

        Returns:
            Dictionary with:
                - exists (bool): Whether document was found
                - doc_id (str): Extracted document ID
                - num_results (int): Number of matching documents
                - title (str): Document title if found
                - url (str): Actual indexed URL if found
        """
        doc_id = self.extract_doc_id_from_url(url)
        if not doc_id:
            return {
                "exists": False,
                "doc_id": None,
                "num_results": 0,
                "error": "Could not extract document ID from URL",
            }

        # Query Solr for documents matching this ID
        # Use wildcard search on id field (most reliable)
        query = f"id:*{doc_id}*"

        try:
            params = {
                "q": query,
                "rows": 5,  # Get a few results to handle duplicates
                "fl": "id,title,url,documentKind",  # Fields to return
                "wt": "json",
            }

            response = requests.get(self.select_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            num_results = data["response"]["numFound"]

            result = {
                "exists": num_results > 0,
                "doc_id": doc_id,
                "num_results": num_results,
                "query": query,
            }

            if num_results > 0:
                # Return first matching doc
                doc = data["response"]["docs"][0]
                result["title"] = doc.get("title", "")
                result["url"] = doc.get("url", "")
                result["documentKind"] = doc.get("documentKind", "")
                result["id"] = doc.get("id", "")

            return result

        except requests.RequestException as e:
            return {
                "exists": False,
                "doc_id": doc_id,
                "num_results": 0,
                "error": f"Solr query failed: {str(e)}",
            }

    def suggest_urls_for_query(self, query: str, max_results: int = 5) -> List[Dict]:
        """Suggest relevant URLs for a user query by searching Solr.

        Useful when expected_urls are missing from test config.

        Args:
            query: User query text
            max_results: Maximum number of URLs to suggest

        Returns:
            List of dictionaries with suggested documents (url, title, score)
        """
        try:
            params = {
                "q": query,
                "rows": max_results,
                "fl": "id,title,url,documentKind,score",
                "wt": "json",
            }

            response = requests.get(self.select_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            docs = data["response"]["docs"]

            suggestions = []
            for doc in docs:
                suggestions.append(
                    {
                        "url": doc.get("url", ""),
                        "title": doc.get("title", ""),
                        "documentKind": doc.get("documentKind", ""),
                        "score": doc.get("score", 0.0),
                    }
                )

            return suggestions

        except requests.RequestException as e:
            print(f"Warning: Could not query Solr for suggestions: {e}")
            return []

    def check_all_expected_urls(self, expected_urls: List[str]) -> Dict[str, Dict]:
        """Check if all expected URLs exist in Solr.

        Args:
            expected_urls: List of expected URLs

        Returns:
            Dictionary mapping URL -> check result
        """
        results = {}
        for url in expected_urls:
            results[url] = self.check_document_exists(url)
        return results

    def get_missing_urls(self, expected_urls: List[str]) -> List[str]:
        """Get list of expected URLs that are missing from Solr.

        Args:
            expected_urls: List of expected URLs

        Returns:
            List of URLs not found in Solr
        """
        missing = []
        for url in expected_urls:
            result = self.check_document_exists(url)
            if not result["exists"]:
                missing.append(url)
        return missing


if __name__ == "__main__":
    # Quick test
    checker = SolrDocumentChecker()

    if not checker.is_available():
        print("❌ Solr is not available at http://localhost:8983/solr/portal")
        exit(1)

    print("✅ Solr is available\n")

    # Test with a known URL
    test_url = "access.redhat.com/solutions/2726611"
    print(f"Checking: {test_url}")
    result = checker.check_document_exists(test_url)
    print(f"  Exists: {result['exists']}")
    if result["exists"]:
        print(f"  Title: {result.get('title', 'N/A')}")
        print(f"  URL: {result.get('url', 'N/A')}")
    print()

    # Test URL suggestions
    query = "Can I run a RHEL 6 container on RHEL 9?"
    print(f"Suggesting URLs for: {query}")
    suggestions = checker.suggest_urls_for_query(query, max_results=3)
    for i, doc in enumerate(suggestions, 1):
        print(f"  {i}. {doc['url']}")
        print(f"     {doc['title']}")
        print(f"     Score: {doc['score']:.2f}")
