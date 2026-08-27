FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SEM_EDS_CORE_HOST=0.0.0.0 \
    SEM_EDS_CORE_PORT=8080

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser
USER 10001

EXPOSE 8080

CMD ["sem-eds-core-api"]
