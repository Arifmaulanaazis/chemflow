# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openbabel libxrender1 libxext6 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY chemflow ./chemflow
COPY --from=frontend /chemflow/web/static ./chemflow/web/static
RUN pip install --no-cache-dir ".[web]" && useradd --create-home --uid 10001 chemflow && mkdir /data && chown chemflow /data
USER chemflow
# Bake AutoDock Vina into the image so docking works offline, out of the box.
RUN python -c "from chemflow.docking.vina_manager import VinaReleaseManager; print(VinaReleaseManager().resolve())"
ENV MPLBACKEND=Agg PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000
CMD ["python", "-m", "chemflow", "web", "--host", "0.0.0.0", "--workspace", "/data"]
