# AI Platform — Vault de Conocimiento

Este vault de Obsidian es la base de conocimiento interna de la organización.

## Estructura

```
obsidian-vault/
├── _templates/          # Plantillas de notas. No se ingestan en RAG.
├── inbox/               # Captura rápida sin estructurar. Vaciar regularmente.
├── knowledge/           # Base de conocimiento permanente y curada.
│   ├── processes/       # Procesos y procedimientos internos.
│   ├── technical/       # Documentación técnica e infraestructura.
│   └── products/        # Información de productos y servicios.
├── projects/            # Notas activas por proyecto.
└── meetings/            # Actas de reuniones.
```

## Convenciones

- Una nota = un tema
- Frontmatter YAML con `tags`, `area` y `estado` en cada nota
- Usar links `[[Nota]]` para conectar ideas relacionadas
- Títulos descriptivos (no "Reunión" sino "Reunión kick-off proyecto X 2026-04-24")

## Lo que NO debe estar aquí

- Contraseñas o secretos
- Datos personales de clientes (LOPD)
- Borradores temporales (usar `inbox/` y procesarlos)

## Integración con IA (Fase 2)

El sistema leerá este vault y lo indexará en Qdrant para responder preguntas
con contexto real de la organización. Ver [docs/obsidian-knowledge-base.md](../docs/obsidian-knowledge-base.md).
