FROM python:3.12-slim

WORKDIR /app

# Install Node.js for the DeepBridge PoW bridge (node_pow_bridge.mjs).
RUN apt-get update && apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e '.'

COPY . .

# Create non-root user.
RUN useradd -m -u 1000 gtg && chown -R gtg:gtg /app
USER gtg

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
