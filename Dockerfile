# Dogear: one small image for 64-bit ARM (Odroid, Raspberry Pi) and x86.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOGEAR_RECIPES=/recipes \
    DOGEAR_DATA=/data \
    DOGEAR_WEB=/app/web

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY dogear ./dogear
RUN pip install .
COPY web ./web

RUN useradd --uid 1000 --create-home dogear \
    && mkdir -p /recipes /data && chown dogear:dogear /recipes /data
USER dogear

VOLUME ["/recipes", "/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["python", "-m", "dogear", "serve", "--host", "0.0.0.0", "--port", "8000"]
