"""
main.py — FastAPI application entry point.

Routes:
  GET  /        → health check
  POST /agent   → main agent endpoint

This module handles only HTTP concerns: request validation, response shaping,
and error mapping. All intelligence lives in agent.py and mcp_client.py.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from typing import Any

from agent import run_agent

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MCP-Style Gemini Agent",
    description=(
        "A production-ready AI agent that uses a Model Context Protocol (MCP) "
        "tool layer to fetch real-world data, then synthesizes a final answer "
        "using Google Gemini."
    ),
    version="1.0.0",
)


# ── Schemas ───────────────────────────────────────────────────────────────────
class AgentRequest(BaseModel):
    input: str

    @field_validator("input")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("'input' must not be empty or whitespace.")
        return v.strip()


class AgentResponse(BaseModel):
    input: str
    tool_used: str
    tool_data: Any          # dict | None — raw MCP output, kept for transparency
    response: str


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", summary="Health check")
def health() -> dict[str, str]:
    """Confirms the service is running. Used by Cloud Run health probes."""
    return {"status": "ok", "service": "MCP-Style Gemini Agent"}


@app.post("/agent", response_model=AgentResponse, summary="Run the AI agent")
async def agent_endpoint(body: AgentRequest) -> AgentResponse:
    """
    Accepts a plain-text question or instruction, routes it through the
    MCP tool layer for context, and returns a Gemini-generated answer.

    Example request body:
        { "input": "Who was Marie Curie?" }

    Example response:
        {
          "input": "Who was Marie Curie?",
          "tool_used": "wikipedia",
          "tool_data": { "title": "Marie Curie", "extract": "..." },
          "response": "Marie Curie was a pioneering physicist and chemist..."
        }
    """
    try:
        result = await run_agent(body.input)
        return AgentResponse(**result)

    except EnvironmentError as exc:
        # GOOGLE_API_KEY not set
        raise HTTPException(status_code=500, detail=str(exc))

    except ValueError as exc:
        # Bad input caught at agent layer
        raise HTTPException(status_code=422, detail=str(exc))

    except Exception as exc:
        # Catch-all: log in production, return safe message to client
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {str(exc)}",
        )
