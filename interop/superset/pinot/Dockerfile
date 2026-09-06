FROM apache/superset:6.1.0

USER root
RUN . /app/.venv/bin/activate && uv pip install "pinotdb==9.1.2"
USER superset
