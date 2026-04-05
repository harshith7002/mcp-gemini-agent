# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/build/deps -r requirements.txt


# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.11-slim

# Run as non-root user — security best practice
RUN useradd --create-home appuser
WORKDIR /home/appuser

# Copy installed packages from builder stage
COPY --from=builder /build/deps /usr/local

# Copy only the application source (no dev files, no tests)
COPY main.py agent.py mcp_client.py ./

USER appuser

# Cloud Run injects PORT=8080 automatically; we honour it explicitly
ENV PORT=8080
EXPOSE 8080

# GOOGLE_API_KEY must be set at runtime via:
#   - gcloud run deploy --set-env-vars
#   - Cloud Run secret references (recommended for production)
# Never bake API keys into the image.

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
