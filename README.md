# Nemotron 3.5 ASR para Docker y Portainer

> **Versión actual:** dos contenedores (`gateway` + `engine`). Si ya tenés el stack anterior en Portainer, actualizá **ese mismo stack** para conservar sus volúmenes `model` y `auth`; no crees otro con el mismo puerto ni borres los volúmenes. El despliegue de Portainer lo hace el usuario.

Servicio de **transcripción de voz en español** con HTTP para archivos/notas de voz y WebSocket para streaming. Ejecuta [NVIDIA Nemotron 3.5 ASR Streaming 0.6B](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) mediante [NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp), detrás de una pasarela que autentica peticiones y convierte formatos con FFmpeg.

```text
Cliente ── HTTP multipart / WebSocket ──► gateway (Bearer + FFmpeg)
                                          │ red interna de Docker
                                          ▼
                                   engine (CUDA + GGUF)
```

- **Dos imágenes y dos contenedores:** [`chmodmasx/nemotron-asr-engine:0.1.0-cuda`](https://hub.docker.com/r/chmodmasx/nemotron-asr-engine) y [`chmodmasx/nemotron-asr-gateway:0.3.0`](https://hub.docker.com/r/chmodmasx/nemotron-asr-gateway) (`linux/amd64`). No hay un tercer contenedor `bootstrap`.
- **Un solo Compose sin `.env` ni variables de stack:** `gateway` descarga/verifica el GGUF Q8 y prepara la clave Bearer en volúmenes persistentes; luego abandona privilegios de root y arranca la API. `engine` espera a que la pasarela indique que terminó esa preparación. El motor monta el modelo en solo lectura y no publica puerto al host. Ni pesos ni claves se incluyen en las imágenes o Git.
- **Contrato acotado:** acepta un subconjunto de las transcripciones de audio de OpenAI. No expone `/v1/chat/completions`, no implementa OpenAI Realtime completo y no vuelve automáticamente compatibles a Hermes, OpenClaw u OpenCode.

## Archivos del proyecto

- `compose.yaml`: despliegue con las dos imágenes publicadas; **no tiene `build:` ni variables externas**.
- `compose.dev.yaml`: desarrollo local; construye desde `engine/` y `gateway/`, sin `.env`.
- `.env.example`: archivo histórico de la versión anterior; **no se necesita para ninguno de los dos Compose**.
- `dockerhub/engine.md` y `dockerhub/gateway.md`: descripciones propias de cada imagen.
- `tests/`: pruebas HTTP y contrato del Compose de Portainer.

## Desarrollo local

Se necesitan Docker Compose y una GPU NVIDIA habilitada para contenedores. Este despliegue se probó en una RTX 3090 compartida; **no** es una garantía de velocidad o memoria en otros equipos.

El Compose de desarrollo usa `127.0.0.1:18091` y el proyecto `nemotron-asr-dev-two` para no competir con Portainer ni con el desarrollo anterior. Descarga y verifica el modelo automáticamente; no pide rutas, clave ni `.env`. Construir y comprobar:

```bash
docker compose --env-file /dev/null -f compose.dev.yaml config --quiet
docker compose --env-file /dev/null -f compose.dev.yaml up -d --build
docker compose --env-file /dev/null -f compose.dev.yaml ps -a
curl -fsS http://127.0.0.1:18091/ready
python -m unittest discover -s tests -p 'test_*.py' -v
```

Las pruebas de contrato leen la clave directamente del contenedor de desarrollo en memoria y no la imprimen. El motor no detiene otros procesos que utilicen la GPU. No borrar volúmenes si se desea conservar el modelo o la clave.

## API de archivos / notas de voz

La pasarela acepta cualquier *formato de audio que FFmpeg instalado pueda decodificar*, incluidos WAV, MP3 y OGG/Opus; lo convierte a WAV PCM16 mono de 16 kHz antes de enviarlo al motor. La ruta es un **subconjunto** de la API de transcripciones de OpenAI. Los campos son `file` (multipart), `model` (`default`), `language` (por defecto `es-US`; `es` se normaliza a `es-US`) y los campos admitidos por el motor; el resultado JSON usual tiene `{"text":"..."}`.

```bash
curl -fsS -H 'Authorization: Bearer TU_CLAVE_GENERADA' \
  -F 'model=default' -F 'language=es' \
  -F 'file=@/ruta/al/audio.ogg' \
  'http://SERVIDOR:18090/v1/audio/transcriptions'
```

La clave del ejemplo se consulta en Portainer como se indica más abajo; **no copiarla al repositorio**. Sustituí `SERVIDOR` por el nombre o la dirección del equipo **solo en tu cliente**, no en este repositorio. Para un cliente que admite la API de audio de OpenAI, configurar URL base `http://SERVIDOR:18090/v1`, clave Bearer, ruta `/audio/transcriptions` y modelo `default`. **No** ofrece `/v1/chat/completions` ni otras rutas de LLM; tampoco se ha probado la integración directa con OpenClaw, OpenCode o Hermes. Cada harness podría necesitar un adaptador si no permite configurar su endpoint de STT por separado.

## Streaming

WebSocket: `ws://HOST:PUERTO/v1/audio/transcriptions/realtime`, con cabecera `Authorization: Bearer TU_CLAVE_GENERADA`. Se conecta al protocolo de NeMo-Speech.cpp: tras `session.created`, el cliente puede enviar `{"type":"session.update","session":{"language":"es-US","sample_rate":16000}}`; a continuación envía *frames binarios* de PCM16LE mono a 16 kHz y termina con `{"type":"input_audio_buffer.commit"}`. La respuesta final tiene tipo `conversation.item.input_audio_transcription.completed` y un campo `transcript`. El proxy WebSocket **no convierte OGG/MP3 en streaming**: el cliente debe entregar PCM16LE. **No es** la API OpenAI Realtime completa.

## Seguridad y operación

- Acceso: el Compose de Portainer publica `0.0.0.0:18090`, es decir, **todas las interfaces del host**; el desarrollo local escucha solo en `127.0.0.1:18091`. El motor permanece en la red interna de Docker. Protegé el host con firewall/VPN si no querés que la API quede accesible desde otras redes.
- HTTP y WS **no usan TLS**: no cruzar redes no confiables con esta clave. Si se requiere acceso remoto, agregar VPN o proxy TLS antes de ampliar la exposición. No poner la clave en la URL ni en un repositorio.
- `/health` y `/ready` son públicos para las sondas; las rutas `/v1/*` exigen Bearer.
- Requisitos: Docker Compose, runtime NVIDIA GPU y GPU con memoria libre suficiente. Comprobar el uso antes de levantar el stack; no detiene otros procesos de GPU.
- El GGUF deriva del [modelo NVIDIA sujeto a OpenMDW 1.1](https://openmdw.ai/license/1-1/); las imágenes no incluyen pesos. El binario del motor procede del release de [NeMo-Speech.cpp v0.1.0](https://github.com/NVIDIA/NeMo-Speech.cpp/releases/tag/v0.1.0) (Apache-2.0 y avisos de terceros incluidos en el paquete). El proyecto no declara todavía una licencia propia para la pasarela: no asumir derechos de redistribución más allá de los permisos expresos de cada componente.
- Límites de la pasarela: carga de entrada 64 MiB, WAV convertido 52 MiB, y conversión con tope de 900 s / 90 s de proceso. La disponibilidad de un formato depende de FFmpeg.
- Pruebas de contrato local: `python -m unittest discover -s tests -p 'test_*.py' -v` con `compose.dev.yaml` levantado. Se ejercitó además con una nota de voz humana en español vía HTTP y WebSocket y con dos solicitudes simultáneas; esto no constituye una evaluación estadística de precisión ni una garantía de latencia.

## Entrega para Portainer (Docker Standalone)

[`compose.yaml`](compose.yaml) de `main` descarga las dos imágenes y **no tiene `build:`, `.env`, interpolaciones, bind mounts de host ni direcciones privadas fijadas**. Usar Docker Standalone con GPU NVIDIA; no se verificó en Swarm. **Publicar el archivo no actualiza por sí solo el stack de Portainer:** esa migración la realiza el usuario.

1. Para una instalación nueva, usar el Compose enlazado arriba. Si ya existe el stack `nemotron-asr`, actualizar **ese mismo stack** en Portainer con el Compose completo; no crear otro con el mismo puerto `18090`. No añadir variables ni un `.env`. Al editar el stack anterior, activar **Prune services** para retirar únicamente el antiguo contenedor `bootstrap` ya finalizado; **no** eliminar el stack ni sus volúmenes. Podría haber una interrupción breve.
2. `gateway` inicializa el GGUF Q8 desde una revisión fijada de Hugging Face en un volumen persistente, comprueba SHA-256 `3fc991d3badad7277c11030a7519832cddaf2057aafed6d4b25147e953a070b1` y crea o reutiliza la clave en otro volumen. La primera descarga (~708 MiB en disco) necesita Internet; los siguientes inicios verifican el modelo guardado sin cambiar la clave. Si falla Internet o el checksum, la API no arranca y el motor queda bloqueado por la dependencia. El proceso de la API corre como UID/GID `65532`, no como root.
3. El puerto se publica como **`0.0.0.0:18090`** (todas las interfaces). Desde un cliente, probar `http://SERVIDOR:18090/ready`, reemplazando `SERVIDOR` por el host correspondiente **en el cliente**, no en GitHub. Ni el motor ni la clave quedan publicados como puertos.
4. Para consultar la clave generada, abrir la **Console** del contenedor `gateway` en Portainer con `/bin/sh` y ejecutar `python -c "from pathlib import Path; print(Path('/run/asr-auth/api_key').read_text().strip())"`. Copiarla directamente al cliente: **no enviarla al chat ni subirla a GitHub**. El volumen `auth` la conserva entre reinicios; eliminarlo la invalida. Solo los administradores de Docker/Portainer pueden acceder a los volúmenes.
5. Configurar en los clientes URL base `http://SERVIDOR:18090/v1`, esa clave Bearer, ruta `/audio/transcriptions` y modelo `default`; verificar cada integración real. `gateway` tiene acceso saliente para la descarga inicial y escritura en los volúmenes durante la preparación; tras bajar privilegios no puede reescribir modelo ni clave (`root:65532`, modo `0640` para la clave). El motor permanece en red interna y monta el modelo en solo lectura.

El Compose de desarrollo usa **otro puerto** (`127.0.0.1:18091`) y otro proyecto/volúmenes, así que no compite por el puerto de Portainer. HTTP y WS en LAN transmiten el token sin cifrar: **no exponer a Internet sin VPN o TLS**. La sonda Docker de `gateway` significa «modelo/clave inicializados y puerto local abierto»; la ruta externa `/ready` comprueba *además* que el motor ya está listo. Conservar los volúmenes de Portainer durante cualquier actualización: contienen el modelo y la clave.

**Si migrás desde la versión anterior:** mantener el nombre del stack para reutilizar sus volúmenes `model` y `auth`; actualizar la imagen a `gateway:0.3.0`, usar **Prune services** al quitar `bootstrap` y comprobar que queden dos contenedores, `/ready` y una transcripción. Esa opción retira el contenedor antiguo, **no** los volúmenes; no elegir «Delete stack» ni «remove volumes». La actualización puede interrumpir brevemente el servicio.

La sintaxis se comprueba sin variables con `docker compose --env-file /dev/null -f compose.yaml config --quiet`. Eso **no demuestra un despliegue desde la UI de Portainer**; esa verificación corresponde a la instalación que realice el usuario.

## Docker Hub y procedencia

Las dos imágenes se distribuyen **sin GGUF ni claves**. Los contextos de construcción se limitan a `./engine` y `./gateway`: ni `.env` ni `models/` entran en las imágenes. Los avisos de licencia del binario NVIDIA viajan en el paquete de runtime. El Dockerfile del motor verifica SHA-256 del release CUDA oficial; la inicialización dentro de `gateway` verifica el GGUF antes de montarlo. El usuario no tiene que indicar rutas de host ni generar claves por su cuenta.

[Descripción del motor en Docker Hub](https://hub.docker.com/r/chmodmasx/nemotron-asr-engine) · [Descripción de la pasarela en Docker Hub](https://hub.docker.com/r/chmodmasx/nemotron-asr-gateway) · [Código fuente en GitHub](https://github.com/chmodmasx/nemotron-asr-0.6b).

Fuentes: [tarjeta del modelo](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) · [API de NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/api.md) · [Stacks de Portainer](https://docs.portainer.io/user/docker/stacks/add).
