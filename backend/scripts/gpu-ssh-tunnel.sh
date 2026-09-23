#!/usr/bin/env bash
set -euo pipefail

# Run on the backend host. The remote inference API must listen on the
# NVIDIA host at 127.0.0.1:GPU_INFERENCE_PORT.
: "${GPU_SSH_HOST:?Set GPU_SSH_HOST to the NVIDIA SSH host}"
: "${GPU_SSH_USER:?Set GPU_SSH_USER to the NVIDIA SSH username}"
: "${GPU_INFERENCE_PORT:?Set GPU_INFERENCE_PORT to the inference HTTP API port on NVIDIA}"

GPU_SSH_PORT="${GPU_SSH_PORT:-22}"
GPU_LOCAL_PORT="${GPU_LOCAL_PORT:-8765}"

exec ssh \
  -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -p "$GPU_SSH_PORT" \
  -L "127.0.0.1:${GPU_LOCAL_PORT}:127.0.0.1:${GPU_INFERENCE_PORT}" \
  "${GPU_SSH_USER}@${GPU_SSH_HOST}"
