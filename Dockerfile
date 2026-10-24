# Dogear: one small image for 64-bit ARM, 32-bit ARM (CoreELEC's Docker
# add-on is 32-bit even on 64-bit boards) and x86.

# Build wheels in a throwaway stage so platforms without prebuilt wheels
# (32-bit ARM) can compile them without keeping a compiler in the image.
FROM python:3.12-slim AS wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libyaml-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY dogear ./dogear
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOGEAR_RECIPES=/recipes \
    DOGEAR_DATA=/data \
    DOGEAR_WEB=/app/web

WORKDIR /app
COPY --from=wheels /wheels /wheels
RUN pip install --no-index --find-links=/wheels dogear && rm -rf /wheels
COPY web ./web

RUN useradd --uid 1000 --create-home dogear \
    && mkdir -p /recipes /data && chown dogear:dogear /recipes /data
USER dogear

VOLUME ["/recipes", "/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["python", "-m", "dogear", "serve", "--host", "0.0.0.0", "--port", "8000"]
