# Official NVIDIA NeMo-Speech.cpp v0.1.0 CUDA release, verified by SHA-256.
# Weights stay outside this image and are mounted read-only at runtime.
FROM debian:bookworm-slim AS fetch
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
ARG ARCHIVE=nemo-speech-0.1.0-linux-x86_64-cuda.tar.gz
ARG ARCHIVE_SHA256=e68628f396489c98fb353e070efaea5bc4977409ae7734fce56c251a79e29147
RUN set -eu; \
    curl --fail --location --retry 3 --output /tmp/release.tar.gz \
      "https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.1.0/${ARCHIVE}"; \
    printf '%s  %s\n' "$ARCHIVE_SHA256" /tmp/release.tar.gz | sha256sum -c -; \
    mkdir -p /opt/nemo; \
    tar -xzf /tmp/release.tar.gz -C /opt/nemo --strip-components=1

FROM debian:bookworm-slim
COPY --from=fetch /opt/nemo /opt/nemo
ENV LD_LIBRARY_PATH=/opt/nemo/lib PATH=/opt/nemo/bin:$PATH HOME=/tmp
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/opt/nemo/bin/nemo-speech"]
