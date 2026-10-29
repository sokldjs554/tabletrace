# TableTrace API + console.
#   docker build -t tabletrace .                       # heuristic planner only (small image, no torch)
#   docker build --build-arg WITH_MODEL=1 -t tabletrace:model .   # + PyTorch/Transformers (mount models/)
FROM python:3.13-slim AS base
ARG WITH_MODEL=0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    TABLETRACE_PLANNER=auto TABLETRACE_MODEL_DIR=models/mt5-small-tabletrace
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e . && \
    if [ "$WITH_MODEL" = "1" ]; then pip install -e ".[model]"; fi
COPY data/ko/documents.jsonl data/ko/
COPY data/chem/documents.jsonl data/chem/
COPY console ./console
ARG COMMIT=unknown
ENV TABLETRACE_COMMIT=$COMMIT
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=3).status==200 else 1)"
CMD ["uvicorn", "tabletrace.service.app:app", "--host", "0.0.0.0", "--port", "8000"]
