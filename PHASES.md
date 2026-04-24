# Fases del proyecto — AI Platform

## Fase 0 — Base operativa (ACTUAL)
**Objetivo:** tener un ChatGPT local funcional vía navegador.

- [x] docker-compose con Open WebUI + Ollama + LiteLLM
- [x] Estructura de carpetas del proyecto
- [x] Vault Obsidian inicial
- [x] Documentación de arquitectura y desarrollo
- [ ] Desplegar en servidor Linux
- [ ] Bajar modelos (llama3.2, codellama, llava)
- [ ] Verificar chat funcional en Open WebUI

## Fase 1 — Backend propio
**Objetivo:** FastAPI propio + persistencia + cache.

- [ ] Añadir PostgreSQL al docker-compose
- [ ] Añadir Redis al docker-compose
- [ ] FastAPI con endpoints básicos de chat
- [ ] Autenticación simple (API key o JWT)
- [ ] Logging de conversaciones en PostgreSQL

## Fase 2 — Base de conocimiento (RAG)
**Objetivo:** los modelos pueden responder con contexto del vault Obsidian.

- [ ] Añadir Qdrant al docker-compose
- [ ] Pipeline de ingesta: Obsidian vault → chunks → embeddings → Qdrant
- [ ] Endpoint en FastAPI que hace retrieval antes de llamar al LLM
- [ ] Integración en Open WebUI vía tool/function

## Fase 3 — Agentes
**Objetivo:** agentes que se delegan tareas y debaten entre sí.

- [ ] LangGraph integrado en el backend
- [ ] Agente general + agente de código + agente de research
- [ ] Protocolo de debate multi-agente
- [ ] Herramientas: búsqueda web, lectura de archivos, consulta a Qdrant

## Fase 4 — Canales externos
**Objetivo:** acceso desde Telegram, WhatsApp y apps internas vía API.

- [ ] Bot de Telegram
- [ ] Gateway WhatsApp (Baileys o equivalente)
- [ ] Webhooks genéricos para apps internas

## Fase 5 — Audio
**Objetivo:** transcripción y síntesis de voz local.

- [ ] Speaches (STT/TTS) en docker-compose
- [ ] Integración con Open WebUI
- [ ] Integración con el backend para agentes de voz
