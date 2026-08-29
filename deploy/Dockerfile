FROM python:3.13-slim

# Copy uv and rclone from their official images
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=rclone/rclone:latest /usr/local/bin/rclone /usr/local/bin/rclone

WORKDIR /app

# Install dependencies first (cached layer). --no-install-project keeps this
# layer independent of src/, so editing a Python file does not re-resolve the
# whole dependency tree. LICENSE comes along because pyproject declares it as a
# license file and the build reads it.
COPY pyproject.toml uv.lock LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code, then install the project itself — this is what puts
# the loci-mcp console script on PATH.
COPY src/ ./src/
COPY deploy/entrypoint.sh ./entrypoint.sh
RUN uv sync --frozen --no-dev

ENV LOCI_TRANSPORT=sse
ENV LOCI_VAULT_ROOT=/vault

EXPOSE 4444

ENTRYPOINT ["sh", "entrypoint.sh"]
