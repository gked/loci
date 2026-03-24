FROM python:3.13-slim

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY api.py ./
COPY loci_mcp/ ./loci_mcp/
COPY tools/ ./tools/
COPY loci-skill/ ./loci-skill/

ENV LOCI_TRANSPORT=sse
ENV LOCI_VAULT_ROOT=/vault

EXPOSE 8000

CMD ["uv", "run", "python", "loci_mcp/server.py"]
