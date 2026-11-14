# Prediction API image (Hugging Face Space, Docker SDK). Expects ./serving_bundle in the
# build context: `python -m procurement_risk export-bundle ...` or `demo-bundle`.
FROM python:3.13-slim

# LightGBM needs the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra api

COPY serving_bundle ./serving_bundle
RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

ENV BUNDLE_DIR=/app/serving_bundle PATH="/app/.venv/bin:$PATH" PORT=7860
EXPOSE 7860
CMD ["uvicorn", "procurement_risk.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860"]
