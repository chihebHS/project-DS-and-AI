# Serveur MCP de RevisIA (couche données : SQLite + ChromaDB), transport streamable HTTP.
# Build (depuis le dossier revisia/) : docker build -f mcp_server/Dockerfile -t revisia-mcp .

FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY mcp_server/requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.12-slim
LABEL org.opencontainers.image.title="revisia-mcp" \
      org.opencontainers.image.description="Serveur MCP RevisIA : cours, graphe de connaissances, recherche RAG"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/app \
    DATA_DIR=/data \
    MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=8765 \
    ANONYMIZED_TELEMETRY=False

RUN useradd --uid 10001 --create-home app && mkdir -p /data && chown app:app /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app mcp_server ./mcp_server
USER 10001

# Télécharge le modèle d'embedding (~80 Mo) pendant le build : pas de téléchargement au démarrage du pod
RUN DATA_DIR=/tmp/warmup python -c "from mcp_server import rag; rag.warmup()" && rm -rf /tmp/warmup

EXPOSE 8765
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4)"
CMD ["python", "-m", "mcp_server"]
