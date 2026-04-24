# Fase 0 — Base operativa

## Objetivo

Tener un ChatGPT local funcional accesible desde el navegador, sin ninguna lógica propia todavía.

## Componentes

| Componente | Imagen Docker                           | Puerto |
|------------|-----------------------------------------|--------|
| Ollama     | ollama/ollama:latest                    | 11434  |
| LiteLLM    | ghcr.io/berriai/litellm:main-latest     | 4000   |
| Open WebUI | ghcr.io/open-webui/open-webui:main      | 3000   |

## Pasos para levantar

### 1. Requisitos en el servidor Linux

```bash
# Docker Engine (si no está instalado)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Docker Compose plugin
sudo apt-get install docker-compose-plugin
```

### 2. Clonar/copiar el proyecto

```bash
git clone <repo-url> /opt/ai-platform
cd /opt/ai-platform
```

### 3. Configurar entorno

```bash
cp .env.example .env
# Editar .env con valores reales
nano .env
```

### 4. Levantar servicios

```bash
docker compose up -d
```

### 5. Bajar modelos en Ollama

```bash
# Modelo general de chat
docker exec -it ollama ollama pull llama3.2

# Modelo de código
docker exec -it ollama ollama pull codellama

# Modelo con visión
docker exec -it ollama ollama pull llava
```

> Los modelos se descargan una sola vez y quedan en el volumen `ollama_data`.
> llama3.2 ≈ 2GB, codellama ≈ 4GB, llava ≈ 4GB

### 6. Verificar

```bash
# Estado de los servicios
docker compose ps

# Logs en tiempo real
docker compose logs -f

# Test rápido a LiteLLM
curl http://localhost:4000/health

# Test chat directo
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model": "chat", "messages": [{"role": "user", "content": "Hola"}]}'
```

### 7. Acceder a Open WebUI

Abrir en el navegador: `http://<ip-servidor>:3000`

En el primer acceso, crear la cuenta de administrador.
Ir a **Settings → Connections** y verificar que aparecen los modelos de LiteLLM.

## Criterios de aceptación

- [ ] `docker compose ps` muestra los 3 servicios en estado `Up`
- [ ] LiteLLM responde en `http://<ip>:4000/health`
- [ ] Open WebUI carga en `http://<ip>:3000`
- [ ] Se puede chatear con los modelos `chat`, `code` y `vision`

## Troubleshooting

**Open WebUI no ve modelos:**
- Verificar que `LITELLM_MASTER_KEY` en `.env` coincide con el usado en Open WebUI
- `docker compose logs litellm` para ver errores de configuración

**Ollama no descarga el modelo:**
- El servidor necesita acceso a internet en el primer pull
- Comprobar espacio en disco: `df -h`

**LiteLLM no conecta con Ollama:**
- Comprobar que Ollama está `healthy`: `docker compose ps`
- Los servicios se comunican por nombre DNS de Docker (`http://ollama:11434`)
