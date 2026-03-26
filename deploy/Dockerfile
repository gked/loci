FROM python:3.13-slim

# Copy uv and rclone from their official images
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=rclone/rclone:latest /usr/local/bin/rclone /usr/local/bin/rclone

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY api.py ./
COPY loci_mcp/ ./loci_mcp/
COPY tools/ ./tools/
COPY loci-skill/ ./loci-skill/
COPY deploy/entrypoint.sh ./entrypoint.sh

ENV LOCI_TRANSPORT=sse
ENV LOCI_VAULT_ROOT=/vault

EXPOSE 4444

ENTRYPOINT ["sh", "entrypoint.sh"]
