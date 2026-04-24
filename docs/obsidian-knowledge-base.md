# Obsidian como base de conocimiento

## Filosofía

Obsidian es la **única fuente de verdad** para el conocimiento interno de la organización.
Los documentos viven en el vault. El sistema de IA los lee, pero nunca los duplica ni los reemplaza.

Ventajas de este enfoque:
- Los humanos editan en Obsidian con una experiencia cómoda y potente
- El vault es portable: son ficheros `.md` en una carpeta
- El pipeline RAG (Fase 2) ingesta el vault y lo indexa en Qdrant
- Si el vault cambia, se re-ingesta; Qdrant es un índice, no la fuente

## Estructura del vault

```
obsidian-vault/
├── _templates/          # Plantillas de notas (no se ingestarán en RAG)
├── inbox/               # Captura rápida, sin estructurar
├── knowledge/           # Base de conocimiento permanente
│   ├── processes/       # Procesos internos
│   ├── technical/       # Documentación técnica
│   └── products/        # Información de productos/servicios
├── projects/            # Notas por proyecto
└── meetings/            # Actas de reuniones
```

## Convenciones para mejorar el RAG (Fase 2)

Cuando llegue el momento de implementar RAG, la calidad de los resultados dependerá
de cómo estén escritas las notas. Estas convenciones ayudan desde ahora:

### Títulos descriptivos
```markdown
# Proceso de alta de nuevo cliente        ✓
# Proceso                                 ✗
```

### Tags semánticos (frontmatter YAML)
```markdown
---
tags: [proceso, clientes, onboarding]
area: ventas
estado: vigente
---
```

### Chunks naturales
Cada nota debería tratar un solo tema. Notas largas sobre múltiples temas
generan chunks ruidosos que reducen la precisión del retrieval.

### Links internos
Los links `[[Nota relacionada]]` de Obsidian se preservarán como metadatos
en Qdrant para mejorar el contexto del retrieval.

### Qué NO poner en el vault
- Contraseñas o secretos (usar un gestor de contraseñas)
- Datos personales de clientes (LOPD/GDPR)
- Borradores temporales (usar `inbox/` y limpiarla regularmente)

## Cómo llegará el vault al servidor (Fase 2)

Opciones para sincronizar el vault de Obsidian con el servidor Linux:

### Opción A — Git (recomendada)
El vault es un repositorio git. El servidor hace `git pull` periódicamente
y el pipeline de ingesta detecta cambios.

```bash
# En el servidor, montar como bind mount en docker-compose:
# volumes:
#   - /opt/ai-platform/obsidian-vault:/vault:ro
```

### Opción B — Obsidian Sync (de pago)
Usar el servicio oficial de Obsidian para sincronizar.
El servidor monta la carpeta sincronizada.

### Opción C — Syncthing
Herramienta open-source de sincronización peer-to-peer.
Buena opción si no se quiere usar git para el vault.

## Arquitectura futura del pipeline RAG (Fase 2)

```
obsidian-vault/
    ↓  (lectura de .md files)
Ingesta pipeline
    ↓  (chunking + embeddings)
Qdrant (vector store)
    ↓  (retrieval semántico)
FastAPI backend
    ↓  (context injection)
LiteLLM → Ollama
```

El pipeline de ingesta (pendiente de implementar) hará:
1. Leer todos los `.md` del vault
2. Parsear frontmatter YAML y extraer metadatos
3. Dividir cada nota en chunks de ~512 tokens con overlap
4. Generar embeddings con un modelo local (ej. `nomic-embed-text` en Ollama)
5. Guardar chunks + embeddings + metadatos en Qdrant
6. En cada consulta al backend: recuperar los N chunks más relevantes
   e incluirlos en el prompt como contexto

**No se implementa en Fase 0. Esta documentación existe para diseñar el vault
correctamente desde el principio.**
