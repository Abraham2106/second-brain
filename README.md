# 🧠 Second Brain: AI Team Assistant (Railway Edition)

Este es el núcleo de la inteligencia del **Second Brain**. Un orquestador multi-agente diseñado para operar sobre vaults de **Obsidian**, permitiendo que un equipo de agentes (Manager, Planner, Builder, Researcher y Critic) colaboren en la creación y edición estructurada de notas y código.

🚀 **Acceso en Vivo**: [https://second-brain-production-53b3.up.railway.app/](https://second-brain-production-53b3.up.railway.app/)

## 🏗️ Arquitectura Desacoplada

Este repositorio forma parte de una arquitectura de microservicios:
1.  **Assistant (Este Repo)**: Maneja la interfaz de usuario (Streamlit), la orquestación de tareas y la persistencia en el Vault.
2.  **[Gemini Proxy Balancer](https://github.com/Abraham2106/gemini-proxy-balancer)**: Un servicio independiente que gestiona la rotación de API Keys y el balanceo de carga para mitigar límites de cuota (429/503).

## ✨ Características Elite

- 🤖 **Multi-Agente Profesional**: Lógica coordinada entre agentes especializados para resolver tareas complejas.
- ✒️ **Edición Quirúrgica (Patch System)**: Modifica tus notas de Obsidian usando parches `unified diff` de alta precisión.
- 🗃️ **Indexación por SQLite**: Todo tu vault (links, tags y contenido) es indexado para que los agentes tengan contexto global.
- 🐳 **Docker Ready**: Configurado para desplegarse instantáneamente en Railway con persistencia de datos.

## 🚀 Despliegue y Configuración

Para correrlo localmente o en la nube, necesitas configurar las siguientes variables de entorno:

```env
# URL de tu instancia de Gemini Proxy Balancer
GEMINI_PROXY_URL="https://tu-proxy.up.railway.app/v1/chat/completions"

# Ruta de tu vault (en Railway usa /app/obsidian-vaults)
OBSIDIAN_VAULT_PATH="/app/obsidian-vaults"
```

### Ejecución con Docker
```bash
docker build -t second-brain .
docker run -p 8501:8501 --env-file .env second-brain
```

## 🛠️ Stack Tecnológico
- **UI**: Streamlit
- **Logic**: Python 3.12 (Layered Architecture)
- **Database**: SQLite
- **Infrastructure**: Docker & Railway
