# Nemotron 3.5 ASR · pasarela de audio

**Imagen:** `chmodmasx/nemotron-asr-gateway:0.3.0` · `linux/amd64`. El tag `0.2.0` corresponde al Compose anterior de tres contenedores; no mezclar configuraciones.

Esta pasarela recibe notas de voz y archivos mediante un subconjunto de la API de transcripción de audio de OpenAI, usa FFmpeg para convertirlos a WAV PCM16 mono de 16 kHz y los envía al [motor CUDA](https://hub.docker.com/r/chmodmasx/nemotron-asr-engine) de [Nemotron 3.5 ASR Streaming 0.6B](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b). Probados WAV, MP3 y OGG/Opus. Los formatos adicionales dependen de los decodificadores instalados en FFmpeg.

## Despliegue recomendado

No ejecutar esta imagen sola: necesita un motor ASR. El [Compose de dos contenedores en `main`](https://github.com/chmodmasx/nemotron-asr-0.6b/blob/main/compose.yaml) despliega motor y pasarela **sin `.env`, variables de stack ni un contenedor `bootstrap`**. La propia pasarela descarga/verifica el GGUF y genera o reutiliza la clave Bearer privada en volúmenes Docker antes de arrancar su API como usuario sin privilegios. El motor espera esa preparación. La pasarela lee la clave desde `/run/asr-auth/api_key`, no desde el YAML público. Puerto interno `8080`; el Compose publica `0.0.0.0:18090` (todas las interfaces del host). Al actualizar un stack anterior, conservar sus volúmenes y retirar el antiguo `bootstrap` desde Portainer.

La clave y el GGUF quedan **fuera de las imágenes y de GitHub**. El [README principal](https://github.com/chmodmasx/nemotron-asr-0.6b#readme) explica cómo consultar la clave en Portainer y conservar los volúmenes durante una migración.

## Uso

```bash
curl -H "Authorization: Bearer ${ASR_API_KEY}" \
  -F 'model=default' -F 'language=es' -F 'file=@audio.ogg' \
  'http://HOST:PUERTO/v1/audio/transcriptions'
```

La respuesta JSON habitual es `{"text":"…"}`. `language=es` se convierte a `es-US`; puede pedirse `es-ES` explícitamente. `/health` y `/ready` son rutas públicas de sondas; `/v1/*` requiere Bearer. La conversión de archivos tiene límite de entrada de 64 MiB, salida WAV de 52 MiB y audio de hasta 900 s.

**Streaming:** `ws://HOST:PUERTO/v1/audio/transcriptions/realtime` reenvía el [protocolo WebSocket de NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/api.md). Enviar **PCM16LE mono/16 kHz** en frames binarios y `input_audio_buffer.commit`; esta vía no convierte OGG/MP3 y no implementa OpenAI Realtime completo.

**Seguridad:** HTTP/WS sin TLS transmiten el token en claro. No abrir directamente a Internet; usar red confiable, VPN o terminación TLS. Solo se publica la pasarela, no el motor. No es un endpoint de `/v1/chat/completions` ni garantiza compatibilidad automática con todos los harnesses.
