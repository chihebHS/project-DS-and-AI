# Backend ClubIA : API FastAPI + agents LangGraph + client MCP (HTTP vers le serveur MCP).
# Build (depuis le dossier clubia/) : docker build -f backend/Dockerfile -t clubia-backend .

FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY backend/requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.12-slim
LABEL org.opencontainers.image.title="clubia-backend" \
      org.opencontainers.image.description="API ClubIA : ingestion LangGraph et chat multi-agents"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MCP_TRANSPORT=http MCP_URL=http://mcp-server:8765/mcp \
    STATE_DIR=/state UPLOAD_TMP_DIR=/tmp

RUN useradd --uid 10001 --create-home app && mkdir -p /state && chown app:app /state
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app backend/app ./app
USER 10001

EXPOSE 8001
VOLUME ["/state"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--forwarded-allow-ips", "*"]
