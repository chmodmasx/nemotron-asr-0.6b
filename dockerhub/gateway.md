# Nemotron 3.5 ASR · pasarela de audio

**Imagen:** `chmodmasx/nemotron-asr-gateway:0.4.0` · `linux/amd64`. El tag `0.2.0` corresponde al Compose anterior de tres contenedores; no mezclar configuraciones. El motor sigue en `chmodmasx/nemotron-asr-engine:0.1.0-cuda`.

Esta pasarela recibe notas de voz y archivos mediante un subconjunto de la API de transcripción de audio de OpenAI, usa FFmpeg para convertirlos a WAV PCM16 mono de 16 kHz y los envía al [motor CUDA](https://hub.docker.com/r/chmodmasx/nemotron-asr-engine) de [Nemotron 3.5 ASR Streaming 0.6B](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b). Probados WAV, MP3 y OGG/Opus. Los formatos adicionales dependen de los decodificadores instalados en FFmpeg.

## Despliegue recomendado

No ejecutar esta imagen sola: necesita un motor ASR. El [Compose de dos contenedores en `main`](https://github.com/chmodmasx/nemotron-asr-0.6b/blob/main/compose.yaml) despliega motor y pasarela **sin archivo `.env` ni un contenedor `bootstrap`**, pero requiere **`ASR_API_KEY`** como variable del stack Portainer o del entorno CLI:

```yaml
environment:
  ASR_API_KEY: '${ASR_API_KEY:?Defini ASR_API_KEY en Portainer o en el entorno}'
```

La propia pasarela descarga/verifica el GGUF y prepara los volúmenes Docker antes de arrancar su API como usuario sin privilegios. El motor espera esa preparación. **`ASR_API_KEY` tiene prioridad sobre `/run/asr-auth/api_key` y no modifica ese archivo.** Solo si la variable está ausente en el runtime se usa la clave persistente, generada automáticamente si hace falta. Una variable presente pero vacía o con whitespace/caracteres de control falla cerrada, sin fallback. El Compose público exige la variable. Puerto interno `8080`; el Compose publica `0.0.0.0:18090` (todas las interfaces del host).

Al actualizar, editar **el mismo stack**, definir `ASR_API_KEY`, volver a descargar la imagen `0.4.0` y conservar sus volúmenes `model` y `auth`; retirar el antiguo `bootstrap` con **Prune services** solo si todavía existe. No borrar el stack ni los volúmenes. Leer el archivo del volumen puede devolver una **clave antigua**, no la efectiva mientras exista el override. Los clientes deben usar la clave configurada en `ASR_API_KEY`.

La clave y el GGUF quedan **fuera de las imágenes y de GitHub**. No pegar el secreto en el YAML público, logs ni chat. Usar una clave larga y aleatoria de caracteres ASCII imprimibles, sin espacios ni caracteres de control. Las variables son visibles para administradores de Docker/Portainer: no equivalen a Docker Secrets. El [README principal](https://github.com/chmodmasx/nemotron-asr-0.6b#readme) explica cómo suministrar la clave privada en Portainer, conservar los volúmenes durante una migración y conectar el STT de Hermes usando su `.env` privado (independiente del stack).

## Construcción local

El repositorio tiene un único `compose.yaml` para despliegue. Para construir las dos imágenes locales, usar [`build.sh`](https://github.com/chmodmasx/nemotron-asr-0.6b/blob/main/build.sh) con `sh ./build.sh`; contiene comandos `docker build` y no despliega ni publica contenedores/imágenes.

## Uso

```bash
curl -H "Authorization: Bearer ${ASR_API_KEY}" \
  -F 'model=default' -F 'language=es' -F 'file=@audio.ogg' \
  'http://HOST:PUERTO/v1/audio/transcriptions'
```

La respuesta JSON habitual es `{"text":"…"}`. `language=es` se convierte a `es-US`; puede pedirse `es-ES` explícitamente. `/health` y `/ready` son rutas públicas de sondas; `/v1/*` requiere Bearer. La conversión de archivos tiene límite de entrada de 64 MiB, salida WAV de 52 MiB y audio de hasta 900 s.

**Streaming:** `ws://HOST:PUERTO/v1/audio/transcriptions/realtime` reenvía el [protocolo WebSocket de NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/api.md). Enviar **PCM16LE mono/16 kHz** en frames binarios y `input_audio_buffer.commit`; esta vía no convierte OGG/MP3 y no implementa OpenAI Realtime completo.

**Seguridad:** HTTP/WS sin TLS transmiten el token en claro. No abrir directamente a Internet; usar red confiable, VPN o terminación TLS. Solo se publica la pasarela, no el motor. No es un endpoint de `/v1/chat/completions` ni garantiza compatibilidad automática con todos los harnesses.
