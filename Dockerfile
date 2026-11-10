FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PAPERLESS_DATA_DIR=/data \
    PAPERLESS_MEDIA_ROOT=/media \
    PAPERLESS_CONSUMPTION_DIR=/consume \
    PAPERLESS_OCR_LANGUAGE=deu+eng \
    PAPERLESS_TIME_ZONE=Europe/Berlin

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
        ghostscript qpdf poppler-utils unpaper pngquant \
        imagemagick libmagic1 fonts-liberation curl tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml README.md ./
RUN python - <<'PY' > /tmp/requirements.txt && uv pip install --system --no-cache -r /tmp/requirements.txt && rm /tmp/requirements.txt
import tomllib
d = tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]
print("\n".join(d + ["granian[uvloop]>=2.7,<2.9"]))
PY

COPY src ./src
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /data /media /consume

WORKDIR /app/src
VOLUME ["/data", "/media", "/consume"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
