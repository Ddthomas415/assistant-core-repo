FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libsndfile1 \
    scrot \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY core/       ./core/
COPY server/     ./server/
COPY assistant_shell/ ./assistant_shell/
COPY evals/      ./evals/
COPY web/        ./web/

RUN pip install --no-cache-dir -e ".[dev]"

RUN mkdir -p workspace .assistant_sessions .assistant_memory

EXPOSE 8000

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
