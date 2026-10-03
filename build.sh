#!/bin/sh
# Build both local images. Does not deploy containers or push to a registry.
set -eu
cd -- "$(dirname -- "$0")"

docker build --tag nemotron-asr-engine:0.1.0-cuda ./engine
docker build --tag nemotron-asr-gateway:0.4.0 ./gateway
