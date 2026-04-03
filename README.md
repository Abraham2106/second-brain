# AI Team Assistant (F2P Edition)

Este proyecto recrea un flujo de automatización de inteligencia artificial donde múltiples agentes colaboran para resolver un problema, basado en un enfoque "Free-to-Play" (F2P). Usa la capa gratuita de **Google AI Studio (Gemini)** para orquestar los agentes y bases de datos locales.**

## Características

- 🧠 **Multi-Agente**: Incluye roles como Manager, Planner, Researcher, Builder y Critic.
- 💾 **Memoria Persistente**: Utiliza SQLite para recordar el contexto de un proyecto.
- ⚙️ **Ejecución de Código**: El Builder puede guardar archivos directamente en una carpeta `.workspace/` y proponer comandos que se ejecutan de manera segura.
- 🛡️ **Seguridad primero**: Un filtro de seguridad requiere confirmación manual introduciendo `y` o `n` en la terminal, asegurando que los scripts no borren cosas o hagan movimientos de red peligrosos sin autorización.

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

## RotaciÃ³n de API Keys (Load Balancer)

Si usas varias llaves, puedes rotarlas automÃ¡ticamente cuando una se queda sin cuota (429 `RESOURCE_EXHAUSTED`).

En tu `.env` puedes definir:

- `GEMINI_API_KEYS="key1,key2,key3"`
- (opcional) `GEMINI_MODELS="gemini-2.5-flash,gemini-2.0-flash-lite"`

El runtime intenta todos los modelos de la llave actual; si todos estÃ¡n agotados/en cooldown, pasa a la siguiente llave y asÃ­ sucesivamente.

## Uso

Simplemente llama al script principal:

```bash
python main.py "Hola equipo, quiero construir un script en python que juegue piedra papel o tijera"
```

El Manager inicializará el trabajo, el Planner definirá los pasos, y el Builder empezará a generar el código guardándolo en `/.workspace/`.
