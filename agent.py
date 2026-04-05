"""
agent.py — Reasoning and orchestration layer.

Responsibility: understand intent, decide which MCP tool to call,
combine tool data with user input, and generate a final answer via Gemini.

This module knows nothing about HTTP — that's main.py's job.
This module knows nothing about external APIs — that's mcp_client.py's job.
"""

import os
import json
import re
from typing import Any

import google.generativeai as genai

from mcp_client import call_tool

# ── Gemini setup ──────────────────────────────────────────────────────────────
_model: genai.GenerativeModel | None = None


def _get_model() -> genai.GenerativeModel:
    """
    Lazily initializes the shared Gemini model instance.
    Reads GOOGLE_API_KEY from the environment — never hardcoded.
    """
    global _model
    if _model is None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY environment variable is not set."
            )
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel("models/gemini-2.5-flash")
    return _model


# ── Step 1: Tool selection ─────────────────────────────────────────────────────
_TOOL_DECISION_PROMPT = """
You are a routing assistant. Your only job is to decide which tool to call.

Given the user's input below, respond with a JSON object (and nothing else):
{{
  "tool": "<wikipedia | facts | none>",
  "query": "<search term to pass to the tool, or empty string>"
}}

Rules:
- Use "wikipedia" for questions about people, places, events, history, science, geography.
- Use "facts" for questions specifically about: python, fastapi, gemini, or docker.
- Use "none" if the question is conversational, creative, or needs no external data.
- "query" should be the cleanest possible search term, not the full user sentence.

User input: {user_input}
"""


async def _decide_tool(model: genai.GenerativeModel, user_input: str) -> dict[str, str]:
    """
    Asks Gemini to choose the right tool and query for the user's input.
    Returns {"tool": "...", "query": "..."}.
    Falls back to {"tool": "none", "query": ""} if parsing fails.
    """
    prompt = _TOOL_DECISION_PROMPT.format(user_input=user_input)
    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown fences if Gemini wraps the JSON
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    try:
        decision = json.loads(raw)
        # Validate expected fields
        if "tool" not in decision:
            raise ValueError("Missing 'tool' field")
        return {
            "tool": decision.get("tool", "none"),
            "query": decision.get("query", ""),
        }
    except (json.JSONDecodeError, ValueError):
        # Safe fallback — proceed without a tool rather than crashing
        return {"tool": "none", "query": ""}


# ── Step 2: Final answer generation ───────────────────────────────────────────
_ANSWER_PROMPT = """
You are a knowledgeable and concise assistant. Answer the user's question clearly.

User question:
{user_input}

{tool_section}

Instructions:
- If tool data is provided, use it as your primary source of facts.
- Cite the tool source naturally in your answer when relevant.
- Keep the response clear, accurate, and appropriately detailed.
- Do not mention that you are an AI or that you used a tool unless directly asked.
"""

_TOOL_SECTION_TEMPLATE = """
Relevant context retrieved from the '{source}' tool:
---
{tool_data}
---
"""


def _build_answer_prompt(user_input: str, tool_data: dict[str, Any] | None) -> str:
    """
    Assembles the final prompt by injecting tool data if available.
    If no tool was called (or it errored), the tool section is omitted.
    """
    if tool_data and "error" not in tool_data:
        # Serialize tool data as readable JSON for the model
        tool_json = json.dumps(tool_data, indent=2, ensure_ascii=False)
        source = tool_data.get("source", "external tool")
        tool_section = _TOOL_SECTION_TEMPLATE.format(
            source=source, tool_data=tool_json
        )
    else:
        tool_section = ""  # no context — Gemini answers from its own knowledge

    return _ANSWER_PROMPT.format(user_input=user_input, tool_section=tool_section)


# ── Public agent entry point ───────────────────────────────────────────────────
async def run_agent(user_input: str) -> dict[str, Any]:
    """
    Full agent pipeline:
      1. Decide which tool (if any) to call.
      2. Call the MCP tool and retrieve structured data.
      3. Build a rich prompt combining user input + tool data.
      4. Ask Gemini to generate the final answer.
      5. Return a structured result dict.

    Args:
        user_input: The raw string from the user.

    Returns:
        {
            "input":     original user input,
            "tool_used": tool name that was called (or "none"),
            "tool_data": raw data returned by the tool (or null),
            "response":  final natural-language answer from Gemini
        }
    """
    if not user_input or not user_input.strip():
        raise ValueError("User input cannot be empty.")

    model = _get_model()

    # ── Step 1: Tool decision ──────────────────────────────────────────────────
    decision = await _decide_tool(model, user_input)
    tool_name = decision["tool"]
    tool_query = decision["query"]

    # ── Step 2: Tool call (MCP layer) ─────────────────────────────────────────
    tool_data: dict[str, Any] | None = None
    if tool_name != "none" and tool_query:
        tool_data = await call_tool(tool_name, tool_query)

    # ── Step 3: Final answer via Gemini ───────────────────────────────────────
    answer_prompt = _build_answer_prompt(user_input, tool_data)
    answer_response = model.generate_content(answer_prompt)
    final_answer = answer_response.text.strip()

    return {
        "input": user_input,
        "tool_used": tool_name,
        "tool_data": tool_data,
        "response": final_answer,
    }
