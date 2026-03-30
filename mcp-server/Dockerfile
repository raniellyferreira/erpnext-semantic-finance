# ─── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Instala dependências de compilação (mínimas)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

# ─── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="ERPNext Semantic Finance"
LABEL description="MCP Server para integração com ERPNext - Busca Semântica"

# Instala curl para health check
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Cria usuário não-root
RUN groupadd --gid 1000 mcp && \
    useradd --uid 1000 --gid mcp --shell /bin/bash --create-home mcp

# Copia pacotes Python instalados do builder
COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=mcp:mcp src/ src/

USER mcp

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_SERVER_HOST=0.0.0.0 \
    MCP_SERVER_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=10s --retries=3 --start-period=10s \
    CMD curl -fsSL http://localhost:8000/health || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
