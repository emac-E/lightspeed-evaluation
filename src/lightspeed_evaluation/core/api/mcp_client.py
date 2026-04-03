"""MCP direct client for querying okp-mcp without going through /v1/infer.

This client queries the okp-mcp MCP server directly to retrieve contexts
without needing LLM response generation. Useful for testing retrieval quality.

Unlike the standard API client, this:
- Queries okp-mcp MCP server directly (localhost:8001)
- Does NOT generate LLM responses (response field is None)
- Only retrieves contexts via tool calls
- Works with Ragas metrics that don't need LLM response (context_recall, etc.)
- Builds cache for later evaluation with full metrics

MCP Protocol Flow:
1. Initialize session to get session ID
2. Call tools with session ID in headers
3. Parse SSE (Server-Sent Events) response
"""

import asyncio
import hashlib
import logging
import re
from typing import Any, Optional, cast

import httpx
from diskcache import Cache

from lightspeed_evaluation.core.models import APIConfig, APIRequest, APIResponse
from lightspeed_evaluation.core.system.exceptions import APIError

logger = logging.getLogger(__name__)


class MCPDirectClient:
    """Client for querying okp-mcp MCP server directly."""

    def __init__(
        self,
        config: APIConfig,
    ):
        """Initialize MCP direct client.

        Args:
            config: API configuration
        """
        self.config = config

        # Get MCP URL from config or use default
        mcp_url = config.mcp_url or "http://localhost:8001"
        self.mcp_url = mcp_url.rstrip("/")
        self.timeout = config.timeout
        self.endpoint = f"{self.mcp_url}/mcp"

        # Setup cache
        cache = None
        if config.cache_enabled:
            cache = Cache(config.cache_dir)
        self.cache = cache

        logger.info(f"MCPDirectClient initialized: {self.endpoint}")

    def query(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> APIResponse:
        """Query okp-mcp MCP server to retrieve contexts (synchronous wrapper).

        Args:
            query: User query
            conversation_id: Optional conversation ID (unused in MCP direct)
            attachments: Optional attachments (unused in MCP direct)

        Returns:
            APIResponse with contexts populated but no LLM response

        Raises:
            APIError: If MCP query fails
        """
        return asyncio.run(self._query_async(query, conversation_id, attachments))

    async def _query_async(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> APIResponse:
        """Query okp-mcp MCP server to retrieve contexts.

        Args:
            query: User query
            conversation_id: Optional conversation ID (unused in MCP direct)
            attachments: Optional attachments (unused in MCP direct)

        Returns:
            APIResponse with contexts populated but no LLM response

        Raises:
            APIError: If MCP query fails
        """
        # Prepare request for caching
        api_request = self._prepare_request(query, conversation_id, attachments)

        # Check cache first
        if self.config.cache_enabled:
            cached_response = self._get_cached_response(api_request)
            if cached_response is not None:
                logger.debug("Returning cached response for query: '%s'", query)
                return cached_response

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Step 1: Initialize session to get session ID
                session_id = await self._initialize_session(client)

                # Step 2: Call search_portal tool
                result = await self._call_tool(client, session_id, query)

                # Step 3: Parse contexts from result
                contexts, tool_calls = self._parse_search_portal_result(result, query)

        except httpx.HTTPError as e:
            raise APIError(f"MCP query failed: {e}") from e

        # Build APIResponse
        # NOTE: response is empty string since we're not calling LLM
        response = APIResponse(
            response="",  # Empty string for MCP direct mode (no LLM response)
            tool_calls=tool_calls,
            conversation_id=conversation_id or "mcp-direct",
            input_tokens=0,
            output_tokens=0,
            contexts=contexts,
        )

        # Cache the response
        if self.config.cache_enabled:
            self._add_response_to_cache(api_request, response)

        return response

    async def _initialize_session(self, client: httpx.AsyncClient) -> str:
        """Initialize MCP session and get session ID.

        Args:
            client: HTTP client

        Returns:
            Session ID string

        Raises:
            APIError: If initialization fails
        """
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "lightspeed-eval", "version": "1.0"},
            },
            "id": 1,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        response = await client.post(self.endpoint, json=init_request, headers=headers)
        response.raise_for_status()

        session_id = response.headers.get("mcp-session-id")
        if not session_id:
            raise APIError("No session ID in MCP initialize response")

        logger.debug("MCP session initialized: %s", session_id)
        return session_id

    async def _call_tool(
        self,
        client: httpx.AsyncClient,
        session_id: str,
        query: str,
    ) -> dict[str, Any]:
        """Call search_portal tool via MCP.

        Args:
            client: HTTP client
            session_id: MCP session ID
            query: User query

        Returns:
            Tool result dictionary

        Raises:
            APIError: If tool call fails
        """
        tool_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_portal",
                "arguments": {
                    "query": query,
                    "max_results": 10,
                },
            },
            "id": 2,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
        }

        response = await client.post(self.endpoint, json=tool_request, headers=headers)
        response.raise_for_status()

        # Parse SSE response
        # Format: "event: message\ndata: {json}"
        sse_text = response.text.strip()
        for line in sse_text.split("\n"):
            if line.startswith("data: "):
                import json

                json_str = line[6:]  # Remove 'data: ' prefix
                data = json.loads(json_str)

                # Check for error
                if "error" in data:
                    error_msg = data["error"].get("message", str(data["error"]))
                    raise APIError(f"MCP tool call error: {error_msg}")

                return data.get("result", {})

        raise APIError("No data in MCP SSE response")

    def _parse_search_portal_result(
        self, result: dict[str, Any], query: str
    ) -> tuple[list[str], list[list[dict[str, Any]]]]:
        """Parse search_portal result to extract contexts and build tool_calls structure.

        Args:
            result: MCP tool result dictionary
            query: Original query

        Returns:
            Tuple of (contexts, tool_calls) where:
            - contexts: List of context strings (for Ragas)
            - tool_calls: Nested list structure with URL metadata
        """
        content = result.get("content", [])
        if not content:
            logger.warning("No content in search_portal result")
            return [], [[]]

        # Get text from first content item
        text = content[0].get("text", "")
        if not text:
            logger.warning("Empty text in search_portal result")
            return [], [[]]

        # Split by separator
        docs = text.split("\n---\n")

        contexts = []
        context_dicts = []

        for doc in docs:
            doc = doc.strip()
            if not doc:
                continue

            # Extract title (markdown **title**)
            title_match = re.search(r"\*\*(.+?)\*\*", doc)
            title = title_match.group(1) if title_match else "Untitled"

            # Extract URL
            url_match = re.search(r"URL: (https://[^\s]+)", doc)
            url = url_match.group(1) if url_match else ""

            # Skip sections without URLs (warning headers only)
            if not url:
                continue

            # Extract content (everything after "Content:" or use full doc)
            content_match = re.search(r"Content: (.+)", doc, re.DOTALL)
            content_text = content_match.group(1).strip() if content_match else doc

            # Add to contexts list (for Ragas)
            contexts.append(content_text)

            # Add to context dicts (for tool_calls structure)
            context_dicts.append(
                {
                    "title": title,
                    "url": url,
                    "content": content_text,
                }
            )

        logger.debug("Parsed %d contexts from search_portal result", len(contexts))

        # Build tool_calls structure matching TurnData format
        tool_calls = [
            [
                {
                    "tool_name": "search_portal",
                    "arguments": {
                        "query": query,
                        "max_results": 10,
                    },
                    "result": {
                        "contexts": context_dicts,
                    },
                }
            ]
        ]

        return contexts, tool_calls

    def _prepare_request(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> APIRequest:
        """Prepare API request with common parameters for caching.

        Args:
            query: User query
            conversation_id: Optional conversation ID
            attachments: Optional attachments

        Returns:
            APIRequest object
        """
        return APIRequest.create(
            query=query,
            provider=self.config.provider or "mcp_direct",
            model=self.config.model or "okp-mcp",
            no_tools=False,  # MCP direct always uses tools
            conversation_id=conversation_id,
            system_prompt=self.config.system_prompt,
            attachments=attachments,
        )

    def _get_cache_key(self, request: APIRequest) -> str:
        """Get cache key for the query.

        Uses same logic as standard APIClient for compatibility.

        Args:
            request: API request

        Returns:
            SHA256 hash of request key fields
        """
        request_dict = request.model_dump()
        keys_to_hash = [
            "query",
            "provider",
            "model",
            "no_tools",
            "system_prompt",
            "attachments",
        ]

        values = [str(request_dict.get(k)) for k in keys_to_hash]
        str_request = ",".join(values)
        return hashlib.sha256(str_request.encode()).hexdigest()

    def _add_response_to_cache(
        self, request: APIRequest, response: APIResponse
    ) -> None:
        """Add response to disk cache.

        Args:
            request: API request
            response: API response
        """
        if self.cache is None:
            raise RuntimeError("cache is None, but used")
        key = self._get_cache_key(request)
        self.cache[key] = response

    def _get_cached_response(self, request: APIRequest) -> Optional[APIResponse]:
        """Get response from the disk cache.

        Args:
            request: API request

        Returns:
            Cached response if found, None otherwise
        """
        if self.cache is None:
            raise RuntimeError("cache is None, but used")
        key = self._get_cache_key(request)
        cached_response = cast(Optional[APIResponse], self.cache.get(key))

        # Zero out token counts for cached responses since no API call was made
        if cached_response is not None:
            cached_response.input_tokens = 0
            cached_response.output_tokens = 0

        return cached_response

    def close(self) -> None:
        """Close MCP client and cache."""
        if self.cache:
            self.cache.close()
