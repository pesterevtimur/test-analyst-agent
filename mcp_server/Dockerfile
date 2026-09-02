FROM python:3.12-slim

# The brief pins Python 3.12 while the host runs 3.14. Keeping the server in a
# container settles that without touching the host.

ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md* ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dev]"
COPY semantic ./semantic
COPY tests ./tests

EXPOSE 8080
CMD ["python", "-m", "sap_agent_mcp.server"]
