# Dashboard image: serves app.py on port 8501. Contains the app, the summary tables, the explainer and its knowledge
# base, and the saved result models; no game data. The explainer answers from its sources on its own, or uses a local Ollama model if OLLAMA_URL
# points to one (for example http://host.docker.internal:11434).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app
COPY requirements-app.txt .
RUN pip install -r requirements-app.txt \
    && useradd --create-home --uid 1000 appuser

COPY app.py .
COPY src/chessanalytics/__init__.py src/chessanalytics/explainer.py src/chessanalytics/boards.py \
     src/chessanalytics/models.py src/chessanalytics/
COPY models/ models/
COPY docs/RESULTS.md docs/
COPY docs/knowledge/ docs/knowledge/
COPY docs/tables/ docs/tables/

USER 1000
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"]

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
