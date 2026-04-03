![AI Team Assistant](file:///c:/Users/solan/Documents/Personal/ai-team-assistant/image.jpg)

# AI Team Assistant (Elite Edition)

Este proyecto recrea un flujo de automatización de inteligencia artificial donde múltiples agentes colaboran para resolver problemas complejos, optimizado para el ecosistema **Obsidian** y basado en un enfoque "Free-to-Play" (F2P).

## Características Elite

- 🧠 **Multi-Agente Profesional**: Manager, Planner, Researcher, Builder y Critic operando con lógica "Token-Hungry" para máxima profundidad.
- ✒️ **Edición Quirúrgica (Patch System)**: Edita notas existentes mediante parches `unified diff`, evitando sobreescrituras accidentales y manteniendo el historial de cambios.
- 💾 **Memoria Relacional Profunda**: SQLite indexa todo el vault (notas, links, tags y assets como scripts o JSON), permitiendo al Planner razonar sobre la estructura completa.
- 💎 **Estándar Obsidian Premium**: Generación automática de **Properties (YAML)**, uso de Callouts avanzados y diagramas **Mermaid** integrados.
- ⚖️ **Gemini Load Balancer**: Rotación inteligente entre múltiples API Keys y modelos para mitigar los límites de la capa gratuita (429/503).
- 🛡️ **Seguridad Local**: Registro de auditoría de todas las ediciones de archivos y confirmación manual de comandos bash.

## Instalación

1. Asegúrate de tener Python instalado (3.10+ recomendado).
2. Clona este repositorio y crea el entorno virtual:
   ```bash
   python -m venv venv
   # Activa en windows = .\venv\Scripts\activate
   # Activa en mac/linux = source venv/bin/activate
   pip install google-generativeai python-dotenv colorama
   ```
3. Renombra `.env.example` a `.env` y pega tu `GEMINI_API_KEY` (Sácala de [Google AI Studio](https://aistudio.google.com/app/apikey)).

## Rotación de API Keys (Load Balancer)

Si usas varias llaves, puedes rotarlas automáticamente cuando una se queda sin cuota (429 `RESOURCE_EXHAUSTED`).

En tu `.env` puedes definir:

- `GEMINI_API_KEYS="key1,key2,key3"`
- (opcional) `GEMINI_MODELS="gemini-2.5-flash,gemini-2.0-flash-lite"`

El runtime intenta todos los modelos de la llave actual; si todos están agotados/en cooldown, pasa a la siguiente llave y así sucesivamente.

## Uso

Simplemente llama al script principal:

```bash
python main.py "Hola equipo, quiero construir un script en python que juegue piedra papel o tijera"
```

El Manager inicializará el trabajo, el Planner definirá los pasos, y el Builder empezará a generar el código guardándolo en `/.workspace/`.
