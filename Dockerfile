FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .
COPY wishlist.yaml ./wishlist.yaml

# Run as a normal user. UID 1000 is the default user on Raspberry Pi OS,
# so the ./data folder on the host stays writable.
RUN useradd --uid 1000 --create-home app && mkdir -p /app/data && chown app /app/data
USER app

CMD ["python", "-m", "gamealert", "serve", "--config", "/config/config.yaml"]
