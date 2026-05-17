# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

# Install uv from its official image
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /opt/expdeploy

# Install Python deps first (cache layer)
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv sync --frozen --no-dev --extra supabase \
    && rm -rf /root/.cache/uv

# Non-root for HPC / Apptainer compatibility
RUN useradd -m -u 1000 expdeploy
USER expdeploy

ENV PYTHONUNBUFFERED=1 \
    EXPDEPLOY_DATA_DIR=/data \
    EXPDEPLOY_HOST=0.0.0.0

EXPOSE 8080
VOLUME ["/data", "/experiments"]

ENTRYPOINT ["uv", "run", "--no-sync", "expdeploy"]
CMD ["--help"]

LABEL org.opencontainers.image.title="expdeploy" \
      org.opencontainers.image.source="https://github.com/lobennett/expdeploy" \
      org.opencontainers.image.licenses="MIT"
