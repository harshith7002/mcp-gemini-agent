# Stage 1: install dependencies 
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/build/deps -r requirements.txt


# Stage 2: lean runtime image
FROM python:3.11-slim

# Run as non-root user — security best practice
RUN useradd --create-home appuser
WORKDIR /home/appuser

COPY --from=builder /build/deps /usr/local


COPY main.py agent.py mcp_client.py ./

USER appuser

# Cloud Run injects PORT=8080 automatically
ENV PORT=8080
EXPOSE 8080



CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
