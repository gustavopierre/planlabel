# Imagem do Plan Labeler para o teste na VPS 3 (ARCHITECTURE §5). Sem segredos aqui:
# as variáveis vêm do env_file do compose (/opt/planlabel/app.env no servidor).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY planlabel ./planlabel
RUN pip install . \
    && useradd --uid 10001 --create-home planlabel \
    && mkdir -p /app/data \
    && chown planlabel:planlabel /app/data

USER planlabel
ENV PLANLABEL_HOST=0.0.0.0 \
    PLANLABEL_PORT=8000 \
    PLANLABEL_DB_PATH=/app/data/labels.sqlite3
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["python", "-m", "planlabel"]
