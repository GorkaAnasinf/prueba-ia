# PROJECT_CONTEXT.md

## Objetivo

Quiero construir una plataforma local de IA para mi organización, ejecutada íntegramente en Linux con Docker, desarrollada desde Windows usando VS Code + Remote SSH.

La idea es crear una especie de “ChatGPT local vitaminado” para evitar fugas de datos, reducir costes y centralizar capacidades de IA internas.

## Capacidades deseadas

El sistema debe permitir:

- Chat tipo ChatGPT vía navegador.
- Uso de varios LLM locales.
- Un modelo para chat general.
- Un modelo especializado en programación.
- Un modelo con visión para analizar imágenes.
- Transcripción de audio a texto.
- Texto a voz.
- Agentes que puedan delegarse tareas entre ellos.
- Agentes que puedan debatir/razonar entre sí antes de responder si se les pide.
- Base de conocimiento interna usando Obsidian.
- Memoria/RAG sobre documentos internos.
- Acceso desde:
  - navegador
  - Telegram
  - WhatsApp
  - aplicaciones internas propias mediante API/webhooks

## Stack preferido

Base:

- Docker Compose
- Open WebUI como interfaz principal
- Ollama inicialmente para modelos locales
- LiteLLM como router/proxy compatible con OpenAI
- Speaches para STT/TTS local
- LangGraph para agentes
- FastAPI como backend propio
- PostgreSQL para persistencia
- Redis para colas/cache
- Qdrant para memoria/RAG/vector store
- Obsidian como vault de conocimiento interno

Canales:

- Telegram mediante Bot API
- WhatsApp preferiblemente mediante OpenClaw o Baileys, sin API oficial de Meta
- OpenClaw solo debe usarse como gateway/adaptador de canales, no como cerebro principal

## Principio arquitectónico

OpenClaw no debe ser el núcleo del sistema.

El núcleo debe ser:

- backend propio FastAPI
- LangGraph para agentes
- LiteLLM para enrutar modelos
- Ollama/vLLM/Speaches para ejecución local
- Qdrant + Obsidian para memoria y conocimiento

Arquitectura conceptual:

```text
Open WebUI / Telegram / WhatsApp / Apps internas
                    ↓
        Gateway de canales / API propia
                    ↓
              FastAPI backend
                    ↓
                LangGraph
                    ↓
        RAG / Memoria / Herramientas
                    ↓
        Obsidian Vault + Qdrant + PostgreSQL
                    ↓
                 LiteLLM
                    ↓
     Ollama / vLLM / Speaches / otros servicios locales