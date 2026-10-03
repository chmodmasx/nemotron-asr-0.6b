# Nemotron 3.5 ASR · motor CUDA

**Imagen:** `chmodmasx/nemotron-asr-engine:0.1.0-cuda` · `linux/amd64`.

Este contenedor aloja [NeMo-Speech.cpp v0.1.0](https://github.com/NVIDIA/NeMo-Speech.cpp/releases/tag/v0.1.0) para inferencia con el modelo [NVIDIA Nemotron 3.5 ASR Streaming 0.6B](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b). El binario CUDA oficial se comprueba con SHA-256 durante la construcción. **La imagen no contiene pesos**: el GGUF Q8 se obtiene por separado y se monta en modo lectura.

## Despliegue recomendado

Usar **junto a** [`chmodmasx/nemotron-asr-gateway:0.4.0`](https://hub.docker.com/r/chmodmasx/nemotron-asr-gateway) mediante el [`compose.yaml`](https://github.com/chmodmasx/nemotron-asr-0.6b/blob/main/compose.yaml) del [repositorio del proyecto](https://github.com/chmodmasx/nemotron-asr-0.6b). Este Compose despliega **dos contenedores**, sin archivo `.env`, y requiere **`ASR_API_KEY`** como variable del stack Portainer o del entorno CLI. La pasarela prepara el modelo y la autenticación antes de que el motor arranque. La variable tiene prioridad sobre `/run/asr-auth/api_key` sin modificar ese archivo; una variable vacía o con whitespace/caracteres de control falla cerrada. Solo si está ausente en el runtime se usa la clave persistente automática. El motor permanece en una red interna y la pasarela es el único puerto publicado (`0.0.0.0:18090`). La imagen del motor sigue en `0.1.0-cuda`.

La pasarela descarga un GGUF fijado por revisión y SHA-256 en un volumen Docker persistente. El motor monta ese volumen en modo lectura en `/models/nemotron-3.5-asr-streaming-0.6b.q8_0.gguf` y usa `gpus: all`. **No** hace falta una ruta del host ni `ASR_MODEL_FILE`. Al migrar, actualizar el mismo stack, definir `ASR_API_KEY`, volver a descargar la pasarela `0.4.0` y conservar los volúmenes `model` y `auth`. El archivo de clave del volumen puede contener una clave antigua: los clientes deben usar la configurada en `ASR_API_KEY`. Consultá el [README principal](https://github.com/chmodmasx/nemotron-asr-0.6b#readme) para el procedimiento de Portainer y las pruebas.

## Construcción local

El repositorio tiene un único `compose.yaml` para despliegue. Para construir las dos imágenes locales, usar [`build.sh`](https://github.com/chmodmasx/nemotron-asr-0.6b/blob/main/build.sh) con `sh ./build.sh`; contiene comandos `docker build` y no despliega ni publica contenedores/imágenes.

## Contrato y seguridad

El motor implementa `POST /v1/audio/transcriptions` para **WAV** y un WebSocket de transcripción con protocolo propio. La imagen *gateway* acepta archivos OGG/Opus y MP3 mediante FFmpeg, expone autenticación Bearer y deja el motor sin puerto directo en el host. **No** es un servidor de chat OpenAI ni implementa toda la API Realtime. No publiques el motor directamente en una red no confiable: el Compose recomendado protege el acceso en la pasarela y requiere VPN/TLS si se sale de una LAN confiable.

**Modelo y licencia:** el GGUF no se redistribuye en la imagen y está sujeto a [OpenMDW 1.1](https://openmdw.ai/license/1-1/). El código y los Dockerfiles del proyecto se publican [aquí](https://github.com/chmodmasx/nemotron-asr-0.6b). Revisa también la licencia y avisos del runtime NVIDIA antes de redistribuir variantes.
