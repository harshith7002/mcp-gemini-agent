"""
mcp_client.py — Model Context Protocol (MCP) style tool layer.

Responsibility: fetch structured data from external sources.
The agent calls this module when it needs real-world knowledge.
Intentionally decoupled from agent logic — this is a pure data layer.

Tools exposed:
  - wikipedia_search(query) → structured article summary via Wikipedia REST API
  - get_topic_facts(topic)  → curated structured facts for known topics (offline)
  - call_tool(name, query)  → single dispatcher entry point used by the agent
"""

import httpx
from typing import Any

# Constants
WIKIPEDIA_SEARCH_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
HTTP_TIMEOUT = 10.0  # seconds


# Tool 1: Wikipedia live search
async def wikipedia_search(query: str) -> dict[str, Any]:
    """
    Fetches a structured Wikipedia summary for the given search query.

    Two-step process:
      1. Use the MediaWiki search API to find the best matching page title.
      2. Fetch the REST page summary for that title (clean, structured JSON).

    Returns a flat dict the agent can embed directly into its prompt context.
    Never raises — returns {"error": "..."} on any failure so the agent stays stable.
    """
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:

        # Step 1 — find the best matching article title
        try:
            search_resp = await client.get(
                WIKIPEDIA_SEARCH_API,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 1,       # we only need the top hit
                    "format": "json",
                    "origin": "*",
                },
            )
            search_resp.raise_for_status()
            hits = search_resp.json().get("query", {}).get("search", [])

            if not hits:
                return {"error": f"No Wikipedia results found for: '{query}'"}

            page_title = hits[0]["title"]

        except httpx.HTTPError as exc:
            return {"error": f"Wikipedia search failed: {exc}"}

        # Step 2 — fetch the structured page summary
        try:
            url = WIKIPEDIA_SUMMARY_API.format(title=page_title.replace(" ", "_"))
            summary_resp = await client.get(url)
            summary_resp.raise_for_status()
            data = summary_resp.json()

        except httpx.HTTPError as exc:
            return {"error": f"Wikipedia summary fetch failed: {exc}"}

    # Return only what the agent needs — avoids bloating the prompt context
    return {
        "source": "wikipedia",
        "title": data.get("title", page_title),
        "description": data.get("description", ""),
        "extract": data.get("extract", ""),          # plain-text summary paragraph(s)
        "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "image_url": data.get("thumbnail", {}).get("source"),  # None if no image
    }


# Tool 2: Curated offline fact store
# Add entries here to grow the local knowledge base with zero latency.
_FACT_STORE: dict[str, dict[str, Any]] = {
    "python": {
        "name": "Python",
        "type": "Programming Language",
        "created_by": "Guido van Rossum",
        "year_created": 1991,
        "paradigms": ["object-oriented", "procedural", "functional"],
        "known_for": "readability, vast standard library, dominant AI/ML ecosystem",
        "latest_stable": "3.12",
    },
    "fastapi": {
        "name": "FastAPI",
        "type": "Python Web Framework",
        "created_by": "Sebastián Ramírez",
        "year_created": 2018,
        "known_for": "async-first, auto OpenAPI docs, Pydantic validation",
        "built_on": ["Starlette", "Pydantic"],
    },
    "gemini": {
        "name": "Google Gemini",
        "type": "Large Language Model family",
        "created_by": "Google DeepMind",
        "year_released": 2023,
        "variants": ["Ultra", "Pro", "Flash", "Nano"],
        "known_for": "multimodal reasoning, long context window, Google ecosystem integration",
    },
    "docker": {
        "name": "Docker",
        "type": "Container Platform",
        "created_by": "Docker Inc.",
        "year_created": 2013,
        "known_for": "OS-level containerization, reproducible deployments, image layering",
    },
}


def get_topic_facts(topic: str) -> dict[str, Any]:
    """
    Returns curated structured facts for a known topic from the local store.
    Matching is case-insensitive. Returns {"error": ...} if topic not found.
    """
    key = topic.lower().strip()
    record = _FACT_STORE.get(key)
    if record:
        return {"source": "curated_dataset", "topic": topic, "facts": record}
    return {
        "error": f"No curated facts for '{topic}'. Try the 'wikipedia' tool instead."
    }


# MCP dispatcher — the only function agent.py imports
async def call_tool(tool_name: str, query: str) -> dict[str, Any]:
    """
    Central tool dispatcher. The agent always calls this; it never imports
    individual tool functions directly. This keeps agent ↔ tool coupling minimal.

    Supported tool names:
      "wikipedia" → live Wikipedia lookup
      "facts"     → local curated fact store
    """
    match tool_name:
        case "wikipedia":
            return await wikipedia_search(query)
        case "facts":
            return get_topic_facts(query)
        case _:
            return {
                "error": f"Unknown tool '{tool_name}'. Available tools: wikipedia, facts"
            }
