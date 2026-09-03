FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# The panel reads and writes the same state as the server, so it uses the
# server's store module rather than a second copy of the schema. Two definitions
# of one table is how the panel starts lying about the queue.
COPY mcp_server/pyproject.toml ./mcp_server/
COPY mcp_server/src ./mcp_server/src
COPY control_panel/pyproject.toml ./control_panel/
COPY control_panel/src ./control_panel/src
RUN pip install --no-cache-dir -e ./mcp_server -e "./control_panel[dev]"

COPY control_panel/static ./control_panel/static
COPY control_panel/tests ./control_panel/tests

EXPOSE 8081
CMD ["python", "-m", "sap_agent_panel.app"]
