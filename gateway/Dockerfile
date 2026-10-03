FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir 'aiohttp==3.14.3'
WORKDIR /srv/app
COPY proxy.py bootstrap.py start.py /srv/app/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
EXPOSE 8080
CMD ["python", "/srv/app/start.py"]
