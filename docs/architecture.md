# Arquitectura — AI Platform

## Principio rector

El núcleo del sistema es **nuestro propio backend** (FastAPI + LangGraph).
Ningún servicio de terceros (Open WebUI, Telegram, WhatsApp) toma decisiones de negocio.
Todo canal externo es un adaptador que llega al backend.

## Fase 0 — Arquitectura mínima (actual)

```
Navegador
    ↓
Open WebUI  (interfaz de chat)
    ↓
LiteLLM  (proxy/router compatible OpenAI)
    ↓
Ollama  (ejecución local de modelos)
```

Servicios activos en Fase 0:

| Servicio   | Puerto | Rol                                    |
|------------|--------|----------------------------------------|
| open-webui | 3000   | Interfaz de chat en navegador          |
| litellm    | 4000   | Router de modelos, API OpenAI-compat.  |
| ollama     | 11434  | Servidor de modelos locales            |

## Fase 1 — Con backend propio

```
Navegador / Apps internas
    ↓
Open WebUI  ←→  FastAPI backend  (lógica propia)
                    ↓                ↓
                LiteLLM          PostgreSQL + Redis
                    ↓
                Ollama
```

## Fase 2 — Con RAG

```
Navegador / Apps internas
    ↓
FastAPI backend
    ↓              ↓
LiteLLM        Qdrant  ←  pipeline ingesta  ←  Obsidian vault
    ↓
Ollama
```

## Fase 3+ — Con agentes y canales

```
Open WebUI / Telegram / WhatsApp / Apps internas
                ↓
        FastAPI backend  (gateway de canales)
                ↓
           LangGraph  (orquestación de agentes)
           ↙        ↘
    Herramientas    RAG / Memoria
         ↓              ↓
       LiteLLM        Qdrant
         ↓
  Ollama / vLLM / Speaches
```

## Decisiones de diseño

- **LiteLLM como única puerta al LLM**: todos los servicios (Open WebUI, FastAPI, LangGraph)
  hablan con LiteLLM. Cambiar de Ollama a vLLM o a un API externo no requiere cambiar el código.

- **Open WebUI solo en Fase 0**: a partir de Fase 1, Open WebUI es una opción más de interfaz,
  no el componente central. El backend FastAPI es el verdadero núcleo.

- **Obsidian como única fuente de verdad documental**: los documentos viven en el vault.
  El pipeline RAG los ingesta, pero no los duplica ni los reemplaza.

- **Sin vendor lock-in**: todos los componentes son open-source y sustituibles.
