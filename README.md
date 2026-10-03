# Nemotron 3.5 ASR para Docker y Portainer

Servicio de **transcripción de voz en español** con HTTP para archivos/notas de voz y WebSocket para streaming. Ejecuta [NVIDIA Nemotron 3.5 ASR Streaming 0.6B](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) mediante [NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp), detrás de una pasarela que autentica peticiones y convierte formatos con FFmpeg.

```text
Cliente ── HTTP multipart / WebSocket ──► gateway (Bearer + FFmpeg)
                                          │ red interna de Docker
                                          ▼
                                   engine (CUDA + GGUF)
```

- **Dos imágenes y dos contenedores:** [`chmodmasx/nemotron-asr-engine:0.1.0-cuda`](https://hub.docker.com/r/chmodmasx/nemotron-asr-engine) y [`chmodmasx/nemotron-asr-gateway:0.4.0`](https://hub.docker.com/r/chmodmasx/nemotron-asr-gateway) (`linux/amd64`). No hay un tercer contenedor `bootstrap`.
- **Un solo Compose sin archivo `.env`, con `ASR_API_KEY` obligatoria:** en Portainer se define como variable del stack; desde CLI puede suministrarse en el entorno. `gateway` descarga/verifica el GGUF Q8 y prepara los volúmenes persistentes; luego abandona privilegios de root y arranca la API. La clave suministrada tiene prioridad sobre la del volumen, sin modificarla. `engine` espera a que la pasarela indique que terminó la preparación. El motor monta el modelo en solo lectura y no publica puerto al host. Ni pesos ni claves se incluyen en las imágenes o Git.
- **Contrato acotado:** acepta un subconjunto de las transcripciones de audio de OpenAI. No expone `/v1/chat/completions`, no implementa OpenAI Realtime completo y no vuelve automáticamente compatibles a Hermes, OpenClaw u OpenCode.

## Archivos del proyecto

- `compose.yaml`: despliegue con las dos imágenes publicadas; **no tiene `build:` y requiere la variable externa `ASR_API_KEY`**.
- `build.sh`: comandos `docker build` para construir las dos imágenes locales; no despliega ni publica nada.
- `.env.example`: archivo histórico de la versión anterior; **no se necesita para el Compose actual**.
- `dockerhub/engine.md` y `dockerhub/gateway.md`: descripciones propias de cada imagen.
- `tests/`: pruebas HTTP y contrato del Compose de Portainer.

## Construir las imágenes

El único Compose del repositorio es `compose.yaml`, para desplegar las imágenes publicadas. La construcción local se hace con [`build.sh`](build.sh), que contiene únicamente los comandos de build:

```bash
sh ./build.sh
```

Equivale a:

```bash
docker build --tag nemotron-asr-engine:0.1.0-cuda ./engine
docker build --tag nemotron-asr-gateway:0.4.0 ./gateway
```

Necesita Docker y acceso a las imágenes base/releases si no están en caché. No requiere una clave, archivo `.env`, GPU activa ni pesos GGUF para construir. El script no inicia contenedores de servicio ni publica las imágenes. Las etiquetas locales son distintas de las `chmodmasx/...` de Docker Hub.

### Pruebas

Las pruebas de integración requieren un stack de prueba ya levantado, Docker con GPU NVIDIA disponible y FFmpeg en el host para preparar audio. No usar el stack de producción. Indicar explícitamente el proyecto de prueba, su archivo de despliegue y su URL; cargar su `ASR_API_KEY` en el entorno por un canal privado. Las variables `ASR_TEST_*` solo controlan las pruebas, no son opciones del servicio.

```bash
ASR_TEST_PROJECT=nemotron-asr-tests \
ASR_TEST_COMPOSE="$PWD/compose.yaml" \
ASR_BASE_URL=http://127.0.0.1:18090 \
python -m unittest discover -s tests -p 'test_*.py' -v
```

Ese comando ejecuta pruebas contra el stack indicado; **no lo despliega**. Si el puerto está ocupado por producción, preparar el despliegue de prueba en otro host o puerto y ajustar `ASR_BASE_URL`. Para automatización puede usarse una configuración temporal derivada de `compose.yaml`, sin añadir otro Compose al repositorio ni usarlo para construir. Las pruebas capturan la clave efectiva del gateway en memoria sin imprimirla. No borrar volúmenes ni detener workloads GPU ajenos.

## API de archivos / notas de voz

La pasarela acepta cualquier *formato de audio que FFmpeg instalado pueda decodificar*, incluidos WAV, MP3 y OGG/Opus; lo convierte a WAV PCM16 mono de 16 kHz antes de enviarlo al motor. La ruta es un **subconjunto** de la API de transcripciones de OpenAI. Los campos son `file` (multipart), `model` (`default`), `language` (por defecto `es-US`; `es` se normaliza a `es-US`) y los campos admitidos por el motor; el resultado JSON usual tiene `{"text":"..."}`.

```bash
curl -fsS -H 'Authorization: Bearer TU_CLAVE_GENERADA' \
  -F 'model=default' -F 'language=es' \
  -F 'file=@/ruta/al/audio.ogg' \
  'http://SERVIDOR:18090/v1/audio/transcriptions'
```

La clave del ejemplo debe coincidir con la `ASR_API_KEY` configurada en el stack; **no copiarla al repositorio**. Sustituí `SERVIDOR` por el nombre o la dirección del equipo **solo en tu cliente**, no en este repositorio. Para un cliente que admite la API de audio de OpenAI, configurar URL base `http://SERVIDOR:18090/v1`, clave Bearer, ruta `/audio/transcriptions` y modelo `default`. **No** ofrece `/v1/chat/completions` ni otras rutas de LLM; no se garantiza compatibilidad automática con todos los harnesses. Cada uno podría necesitar un adaptador si no permite configurar su endpoint de STT por separado.

### Hermes: STT de archivos contra un servidor existente

Guardar la clave efectiva del servidor como `NEMOTRON_ASR_API_KEY` en el **`.env` privado del perfil Hermes** (default: `~/.hermes/.env`; confirmar con `hermes config env-path`). Ese archivo de credenciales del cliente es independiente del stack Docker, que **no necesita `.env`**. No guardar la clave literal en YAML ni reemplazar `OPENAI_API_KEY`.

Sobre el perfil autorizado, y reemplazando `SERVIDOR` solo en el cliente:

```bash
hermes config set stt.enabled true
hermes config set stt.provider openai
hermes config set stt.openai.base_url http://SERVIDOR:18090/v1
hermes config set stt.openai.api_key '${NEMOTRON_ASR_API_KEY}'
hermes config set stt.openai.model default
hermes config set stt.openai.language es
hermes config set stt.openai.timeout 180
hermes config set voice.client_direct false
```

Las comillas simples conservan la referencia privada sin expandir el secreto en el shell. Usar HTTPS o VPN fuera de una red confiable. `openai` designa el formato de la API, no requiere enviar el audio a OpenAI. `voice.client_direct=false` pone **STT y TTS** de Desktop en relay por el backend, sin cambiar el proveedor TTS. Nemotron no genera voz. En Desktop esta conexión corresponde a **chained**, no a GPT-Live ni a transcripción parcial en tiempo real; no cambiar el modo de voz sin autorización. Consultar la [documentación actual de Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/tts), recargar el proceso autorizado que consume el perfil y verificar cada superficie con audio real; una prueba de script no demuestra que Telegram o el micrófono Desktop funcionen.

## Streaming

WebSocket: `ws://HOST:PUERTO/v1/audio/transcriptions/realtime`, con cabecera `Authorization: Bearer TU_CLAVE_GENERADA`. Se conecta al protocolo de NeMo-Speech.cpp: tras `session.created`, el cliente puede enviar `{"type":"session.update","session":{"language":"es-US","sample_rate":16000}}`; a continuación envía *frames binarios* de PCM16LE mono a 16 kHz y termina con `{"type":"input_audio_buffer.commit"}`. La respuesta final tiene tipo `conversation.item.input_audio_transcription.completed` y un campo `transcript`. El proxy WebSocket **no convierte OGG/MP3 en streaming**: el cliente debe entregar PCM16LE. **No es** la API OpenAI Realtime completa.

## Seguridad y operación

- Acceso: el Compose de Portainer publica `0.0.0.0:18090`, es decir, **todas las interfaces del host**. El motor permanece en la red interna de Docker. Protegé el host con firewall/VPN si no querés que la API quede accesible desde otras redes.
- HTTP y WS **no usan TLS**: no cruzar redes no confiables con esta clave. Si se requiere acceso remoto, agregar VPN o proxy TLS antes de ampliar la exposición. No poner la clave en la URL ni en un repositorio.
- `/health` y `/ready` son públicos para las sondas; las rutas `/v1/*` exigen Bearer.
- Requisitos: Docker Compose, runtime NVIDIA GPU y GPU con memoria libre suficiente. Comprobar el uso antes de levantar el stack; no detiene otros procesos de GPU.
- El GGUF deriva del [modelo NVIDIA sujeto a OpenMDW 1.1](https://openmdw.ai/license/1-1/); las imágenes no incluyen pesos. El binario del motor procede del release de [NeMo-Speech.cpp v0.1.0](https://github.com/NVIDIA/NeMo-Speech.cpp/releases/tag/v0.1.0) (Apache-2.0 y avisos de terceros incluidos en el paquete). El proyecto no declara todavía una licencia propia para la pasarela: no asumir derechos de redistribución más allá de los permisos expresos de cada componente.
- Límites de la pasarela: carga de entrada 64 MiB, WAV convertido 52 MiB, y conversión con tope de 900 s / 90 s de proceso. La disponibilidad de un formato depende de FFmpeg.
- Pruebas de contrato local: ver la sección «Pruebas» para seleccionar un stack aislado con `compose.yaml`. Se ejercitó además con una nota de voz humana en español vía HTTP y WebSocket y con dos solicitudes simultáneas; esto no constituye una evaluación estadística de precisión ni una garantía de latencia.

## Entrega para Portainer (Docker Standalone)

[`compose.yaml`](compose.yaml) de `main` descarga las dos imágenes y **no tiene `build:`, archivo `.env`, bind mounts de host ni direcciones privadas fijadas**. Sí tiene una interpolación obligatoria para la clave del usuario:

```yaml
environment:
  ASR_API_KEY: '${ASR_API_KEY:?Defini ASR_API_KEY en Portainer o en el entorno}'
```

Usar Docker Standalone con GPU NVIDIA; no se verificó en Swarm. **Publicar el archivo no actualiza por sí solo el stack de Portainer:** esa migración la realiza el usuario.

1. Para una instalación nueva, usar el Compose enlazado arriba. Si ya existe el stack `nemotron-asr`, actualizar **ese mismo stack** en Portainer con el Compose completo; no crear otro con el mismo puerto `18090`. En las variables de entorno del stack, definir **`ASR_API_KEY` (obligatoria)** con una clave privada no vacía, de caracteres ASCII imprimibles, sin espacios ni caracteres de control. No hace falta crear un `.env`. Al actualizar, activar la opción de volver a descargar las imágenes (**Pull latest image**) para obtener `chmodmasx/nemotron-asr-gateway:0.4.0`; el motor sigue en `0.1.0-cuda`. Si todavía existe el antiguo `bootstrap`, usar **Prune services** para retirarlo; **no** eliminar el stack ni sus volúmenes. Podría haber una interrupción breve.
2. `gateway` inicializa el GGUF Q8 desde una revisión fijada de Hugging Face en el volumen `model` y comprueba SHA-256 `3fc991d3badad7277c11030a7519832cddaf2057aafed6d4b25147e953a070b1`. La primera descarga (~708 MiB en disco) necesita Internet; los siguientes inicios verifican el modelo guardado. El volumen `auth` se conserva, pero `ASR_API_KEY` tiene prioridad sobre `/run/asr-auth/api_key` **sin modificar ese archivo**. Solo si la variable está ausente en el runtime se usa el fallback persistente, generado automáticamente si hace falta. Una variable presente pero vacía o con whitespace/caracteres de control falla cerrada: no habilita el fallback. El Compose público exige la variable y rechaza ausencia o vacío antes de arrancar. Si falla Internet o el checksum, la API no arranca y el motor queda bloqueado por la dependencia. El proceso de la API corre como UID/GID `65532`, no como root.
3. El puerto se publica como **`0.0.0.0:18090`** (todas las interfaces). Desde un cliente, probar `http://SERVIDOR:18090/ready`, reemplazando `SERVIDOR` por el host correspondiente **en el cliente**, no en GitHub. Ni el motor ni la clave quedan publicados como puertos.
4. Usar en los clientes la clave privada que configuraste como **`ASR_API_KEY`**; no enviarla al chat ni subirla a GitHub. Leer `/run/asr-auth/api_key` puede devolver una **clave antigua**, no la efectiva mientras exista el override. Conservar `auth`: guarda el fallback para un runtime sin variable, no una copia sincronizada del override. Solo los administradores de Docker/Portainer pueden acceder a los volúmenes y a la configuración del contenedor.
5. Configurar en los clientes URL base `http://SERVIDOR:18090/v1`, la clave Bearer efectiva, ruta `/audio/transcriptions` y modelo `default`; verificar cada integración real. Si elegiste una clave distinta durante la actualización, actualizar también las credenciales privadas de los clientes (en Hermes, `NEMOTRON_ASR_API_KEY`). `gateway` tiene acceso saliente para la descarga inicial y escritura en los volúmenes durante la preparación; tras bajar privilegios no puede reescribir modelo ni clave persistente (`root:65532`, modo `0640` para el archivo de clave). El motor permanece en red interna y monta el modelo en solo lectura.

HTTP y WS en LAN transmiten el token sin cifrar: **no exponer a Internet sin VPN o TLS**. La sonda Docker de `gateway` significa «modelo/clave inicializados y puerto local abierto»; la ruta externa `/ready` comprueba *además* que el motor ya está listo. Conservar los volúmenes de Portainer durante cualquier actualización: contienen el modelo y la clave.

**Si migrás desde la versión anterior:** mantener el nombre del stack para reutilizar sus volúmenes `model` y `auth`; definir `ASR_API_KEY`, actualizar a `gateway:0.4.0` y volver a descargar la imagen. El motor no cambia. Usar **Prune services** solo si hay que quitar `bootstrap` y comprobar que queden dos contenedores, `/ready` y una transcripción autenticada con la clave configurada. Esa opción retira el contenedor antiguo, **no** los volúmenes; no elegir «Delete stack» ni «remove volumes». La actualización puede interrumpir brevemente el servicio.

Desde CLI, suministrar `ASR_API_KEY` en el entorno mediante un canal privado (sin escribirla en el historial) antes de `docker compose --env-file /dev/null -f compose.yaml config --quiet` o `docker compose --env-file /dev/null -f compose.yaml up -d --pull always`. No hace falta un archivo `.env`. Una comprobación de sintaxis **no demuestra un despliegue desde la UI de Portainer**; esa verificación corresponde a la instalación que realice el usuario. Las pruebas requieren seleccionar explícitamente un stack aislado; no crean un despliegue de desarrollo por su cuenta.

## Docker Hub y procedencia

Las dos imágenes se distribuyen **sin GGUF ni claves**. Los contextos de construcción se limitan a `./engine` y `./gateway`: ni `.env` ni `models/` entran en las imágenes. Los avisos de licencia del binario NVIDIA viajan en el paquete de runtime. El Dockerfile del motor verifica SHA-256 del release CUDA oficial; la inicialización dentro de `gateway` verifica el GGUF antes de montarlo. El usuario no tiene que indicar rutas de host; en el stack público sí debe suministrar su clave privada mediante `ASR_API_KEY`.

[Descripción del motor en Docker Hub](https://hub.docker.com/r/chmodmasx/nemotron-asr-engine) · [Descripción de la pasarela en Docker Hub](https://hub.docker.com/r/chmodmasx/nemotron-asr-gateway) · [Código fuente en GitHub](https://github.com/chmodmasx/nemotron-asr-0.6b).

Fuentes: [tarjeta del modelo](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) · [API de NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/api.md) · [Stacks de Portainer](https://docs.portainer.io/user/docker/stacks/add).
