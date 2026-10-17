FROM ghcr.io/astral-sh/uv:0.11.24 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1 SMT_RUNTIME=/data
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --locked --no-dev && useradd --uid 10001 --create-home operator && mkdir /data && chown operator /data
USER operator
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')"]
ENTRYPOINT ["/app/.venv/bin/smt-workbench", "--runtime", "/data"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
