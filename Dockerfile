FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY bot/ bot/
COPY main.py ./

RUN pip install uv && \
    uv sync --frozen --no-dev

USER 1000

CMD [".venv/bin/python", "-m", "bot.main"]
