# Arcane Panel — Hardened Dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx curl unzip ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd -r arcane && useradd -r -g arcane -m -s /bin/bash arcane
ARG XRAY_VERSION=v26.3.27
ARG XRAY_SHA256=23cd9af937744d97776ee35ecad4972cf4b2109d1e0fe6be9930467608f7c8ae
RUN curl -fsSL -o /tmp/xray.zip \
        "https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/Xray-linux-64.zip" \
    && echo "${XRAY_SHA256}  /tmp/xray.zip" | sha256sum -c - \
    && unzip /tmp/xray.zip -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/xray \
    && rm /tmp/xray.zip
RUN mkdir -p /app /app/data /var/log/nginx /var/lib/nginx \
    && chown -R arcane:arcane /app /var/log/nginx /var/lib/nginx /etc/nginx
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=arcane:arcane ./app /app/app
COPY --chown=arcane:arcane ./static /app/static
COPY --chown=arcane:arcane ./nginx.conf /etc/nginx/nginx.conf
COPY --chown=arcane:arcane ./entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh \
    && chmod 700 /app/data \
    && rm -rf /var/cache/apt/* /tmp/*
USER arcane
ENV PORT=8080 NGINX_PORT=8080 APP_PORT=10000 XRAY_API_PORT=10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT}/health || exit 1
CMD ["bash", "/app/entrypoint.sh"]
