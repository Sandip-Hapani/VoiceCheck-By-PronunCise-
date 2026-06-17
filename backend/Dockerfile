# Whisper needs ffmpeg at runtime, so we start from a full Debian slim image.
FROM python:3.11-slim

# ffmpeg is required by openai-whisper for audio decoding.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for better layer caching.
# openai-whisper builds from an sdist whose setup.py imports pkg_resources, so
# the isolated build env must use setuptools < 81 (see constraints.txt).
COPY requirements.txt constraints.txt ./
ENV PIP_CONSTRAINT=constraints.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the Whisper model at build time so cold starts don't pay for it.
# Override with --build-arg WHISPER_MODEL=small etc.
ARG WHISPER_MODEL=base
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN python -c "import whisper; whisper.load_model('${WHISPER_MODEL}')"

COPY app ./app

EXPOSE 8000

# Single worker: the Whisper model is large and loaded per-process.
# Scale out with more Cloud Run instances rather than more workers (see DEPLOYMENT.md).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
