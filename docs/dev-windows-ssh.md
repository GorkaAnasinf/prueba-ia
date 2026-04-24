# Desarrollo desde Windows con VS Code Remote SSH

## Requisitos en Windows

1. **VS Code** — https://code.visualstudio.com
2. **Extensión Remote - SSH** — buscar `ms-vscode-remote.remote-ssh` en el marketplace
3. **OpenSSH client** — viene con Windows 10/11. Verificar:
   ```powershell
   ssh -V
   ```
   Si no está disponible: *Configuración → Aplicaciones → Características opcionales → OpenSSH Client*

## Generar clave SSH (si no tienes)

```powershell
# En PowerShell de Windows
ssh-keygen -t ed25519 -C "tu-email@empresa.com"
# Guardar en C:\Users\<usuario>\.ssh\id_ed25519
```

## Copiar clave pública al servidor Linux

```powershell
# Opción 1: ssh-copy-id (disponible en Git Bash o WSL)
ssh-copy-id usuario@ip-servidor

# Opción 2: manual
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh usuario@ip-servidor "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

## Configurar SSH config en Windows

Crear o editar `C:\Users\<usuario>\.ssh\config`:

```
Host ai-server
    HostName 192.168.x.x        # IP del servidor Linux
    User tu-usuario
    IdentityFile ~/.ssh/id_ed25519
    ForwardAgent yes
```

Verificar conexión:
```powershell
ssh ai-server
```

## Conectar VS Code al servidor

1. Abrir VS Code
2. `Ctrl+Shift+P` → **Remote-SSH: Connect to Host...**
3. Seleccionar `ai-server`
4. VS Code instala el servidor remoto automáticamente
5. **File → Open Folder** → `/opt/ai-platform`

A partir de ahí, el terminal de VS Code (`Ctrl+ñ`) ejecuta comandos directamente en Linux.

## Trabajar con Docker desde el terminal remoto

```bash
# Ver estado de los servicios
docker compose ps

# Levantar
docker compose up -d

# Parar
docker compose down

# Ver logs de un servicio
docker compose logs -f litellm

# Reiniciar un servicio tras cambiar su config
docker compose restart litellm

# Reconstruir el backend tras cambiar código
docker compose build backend
docker compose up -d backend
```

## Port forwarding — acceder a los servicios desde Windows

VS Code hace port forwarding automático de los puertos detectados.
También se puede hacer manualmente:

```
Ctrl+Shift+P → Forward a Port
```

O en el panel **PORTS** de VS Code (parte inferior).

Puertos a redirigir en Fase 0:

| Servicio   | Puerto servidor | URL en Windows           |
|------------|-----------------|--------------------------|
| Open WebUI | 3000            | http://localhost:3000    |
| LiteLLM    | 4000            | http://localhost:4000    |
| Ollama     | 11434           | http://localhost:11434   |

## Configuración recomendada del workspace

Crear `.vscode/settings.json` en el proyecto (no commitear si tiene paths locales):

```json
{
  "editor.formatOnSave": true,
  "files.eol": "\n",
  "editor.tabSize": 4,
  "[yaml]": { "editor.tabSize": 2 },
  "[markdown]": { "editor.wordWrap": "on" }
}
```

> **Importante:** configurar `"files.eol": "\n"` evita que Windows introduzca
> saltos de línea `\r\n` en archivos que Linux ejecutará.

## Extensiones VS Code recomendadas para este proyecto

Instalar en el servidor remoto (VS Code las instala en el lado correcto automáticamente):

- `ms-python.python` — Python / FastAPI
- `ms-python.ruff` — linter Python
- `redhat.vscode-yaml` — YAML (docker-compose, LiteLLM config)
- `ms-azuretools.vscode-docker` — vista de contenedores Docker
- `esbenp.prettier-vscode` — formateo
- `shd101wyy.markdown-preview-enhanced` — preview de Markdown/docs

## Workflow diario típico

```
1. VS Code → Remote SSH → ai-server
2. Abrir terminal integrado
3. cd /opt/ai-platform
4. git pull  (si hay cambios)
5. docker compose up -d  (si no estaba levantado)
6. Editar código en VS Code (sincronizado en tiempo real al servidor)
7. docker compose restart <servicio>  (si cambiaste config)
8. Ver resultado en http://localhost:3000
```
