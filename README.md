# MCP-Style Gemini Agent

A small agent that uses a **Model Context Protocol (MCP)**-inspired architecture: Gemini decides which tool to call, the tool fetches real data, and Gemini writes the final answer from that data.

Built with **FastAPI** · Deployed on **Google Cloud Run**
DEPLOYED LINK: https://mcp-agent-430885511377.us-central1.run.app/

---

## How It Works

```
User Request (POST /agent)
        │
        ▼
  ┌─────────────┐
  │   main.py   │  ← HTTP layer: validates input, shapes response
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │   agent.py  │  ← Reasoning layer
  │             │    1. Ask Gemini: which tool? what query?
  │             │    2. Call mcp_client with decision
  │             │    3. Build rich prompt (input + tool data)
  │             │    4. Ask Gemini to generate final answer
  └──────┬──────┘
         │
         ▼
  ┌──────────────────┐
  │  mcp_client.py   │  ← Tool/data layer (MCP style)
  │                  │    • wikipedia_search() → Wikipedia REST API
  │                  │    • get_topic_facts()  → local structured dataset
  └──────────────────┘
```

### Routing Logic

The agent uses a **two-phase pipeline**:

1. **Tool selection** — Gemini reads the user's question and returns a JSON decision:
   `{ "tool": "wikipedia | facts | none", "query": "search term" }`

2. **Answer generation** — Gemini receives the original question + tool data and produces the final response.

| Tool | Trigger | Data source |
|---|---|---|
| `wikipedia` | People, places, events, science, geography | Wikipedia REST API (live) |
| `facts` | Python, FastAPI, Gemini, Docker | Local curated dataset (offline) |
| `none` | Conversational, creative, or general questions | Gemini's own knowledge |

---

## Project Structure

```
mcp-agent/
├── main.py         # FastAPI app — HTTP routes and schemas
├── agent.py        # Agent logic — tool decision + Gemini orchestration
├── mcp_client.py   # MCP tool layer — Wikipedia + curated dataset
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Local Setup

### Prerequisites
- Python 3.11+
- A [Google AI Studio API key](https://aistudio.google.com/app/apikey)

### Install & run

```bash
# 1. Clone the repo
git clone https://github.com/harshith7002/mcp-gemini-agent.git
cd mcp-gemini-agent

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your API key
export GOOGLE_API_KEY="your_api_key_here"

# 5. Start the server
uvicorn main:app --reload --port 8080
```

Server runs at `http://localhost:8080`
Interactive API docs: `http://localhost:8080/docs`

---

## API Reference

### `GET /`
Health check — used by Cloud Run readiness probes.

```json
{ "status": "ok", "service": "MCP-Style Gemini Agent" }
```

---

### `POST /agent`
Main agent endpoint.

**Request:**
```json
{ "input": "your question or instruction here" }
```

**Response:**
```json
{
  "input": "original user input",
  "tool_used": "wikipedia | facts | none",
  "tool_data": { "...structured data from the tool..." },
  "response": "final natural-language answer from Gemini"
}
```

**Error codes:**
| Code | Meaning |
|---|---|
| 422 | Input is empty or missing |
| 500 | GOOGLE_API_KEY not set, or Gemini/Wikipedia API error |

---

## Example `curl` Requests

### Wikipedia lookup
```bash
curl -X POST http://localhost:8080/agent \
  -H "Content-Type: application/json" \
  -d '{"input": "Tell me about the James Webb Space Telescope"}'
```

### Curated facts
```bash
curl -X POST http://localhost:8080/agent \
  -H "Content-Type: application/json" \
  -d '{"input": "What is FastAPI and what is it built on?"}'
```

### No tool needed (conversational)
```bash
curl -X POST http://localhost:8080/agent \
  -H "Content-Type: application/json" \
  -d '{"input": "Write a haiku about machine learning"}'
```

---

## Deploy to Cloud Run

### Prerequisites
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
- GCP project with billing enabled

### Step 1 — Configure your project

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export SERVICE="mcp-gemini-agent"
export REPO="mcp-agent-repo"

gcloud config set project $PROJECT_ID
```

### Step 2 — Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

### Step 3 — Create an Artifact Registry repository

```bash
gcloud artifacts repositories create $REPO \
  --repository-format=docker \
  --location=$REGION
```

### Step 4 — Build and push the container image

```bash
gcloud builds submit \
  --tag $REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE
```

### Step 5 — Deploy to Cloud Run

```bash
gcloud run deploy $SERVICE \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY="your_api_key_here" \
  --port 8080 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 10
```

> **Production tip:** Use Secret Manager instead of `--set-env-vars` for your API key:
> ```bash
> echo -n "your_api_key" | gcloud secrets create google-api-key --data-file=-
> gcloud run deploy $SERVICE ... \
>   --set-secrets GOOGLE_API_KEY=google-api-key:latest
> ```

### Step 6 — Test your live service

```bash
SERVICE_URL=$(gcloud run services describe $SERVICE \
  --region $REGION --format 'value(status.url)')

echo "Live at: $SERVICE_URL"

curl -X POST $SERVICE_URL/agent \
  -H "Content-Type: application/json" \
  -d '{"input": "Who invented the telephone?"}'
```

### Teardown

```bash
gcloud run services delete $SERVICE --region $REGION
gcloud artifacts repositories delete $REPO --location=$REGION
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Google AI Studio or Vertex AI API key |
| `PORT` | No | Server port (Cloud Run sets this to `8080` automatically) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| AI Model | Google Gemini 1.5 Pro |
| AI SDK | `google-generativeai` |
| HTTP client (MCP tools) | `httpx` (async) |
| Web Framework | FastAPI + Uvicorn |
| Data validation | Pydantic v2 |
| Deployment | Google Cloud Run |
| Container | Docker (multi-stage, non-root) |
