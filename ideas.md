# 💡 Roadmap & Ideas Para el AI Team Assistant (F2P)

Dado que los límites de la capa gratuita (Rate Limits) son el principal cuello de botella, aquí hay una propuesta para escalar el sistema sin gastar un centavo.

## 1. ⚖️ Orquestador de Proveedores (Smart Load Balancer)
Implementar una capa de abstracción sobre los agentes que gestione automáticamente el "Failover".

**Flujo de Lógica:**
1. **Intento 1**: Enviar a `Gemini 2.0 Flash` (Mejor calidad/velocidad).
2. **Error 429?**: Capturar excepción y rotar a la siguiente API Key de Gemini.
3. **Límite Global?**: Cambiar de proveedor (ej: Groq o Ollama).
4. **Éxito**: Guardar el mensaje en SQLite independientemente del proveedor usado.

### Proveedores Sugeridos (Capa Gratuita)
*   **Google AI Studio (Gemini)**: Hasta 15 RPM (Requests Per Minute) gratis.
*   **Groq**: Velocidad extrema. Soporta Llama 3.1 y Mixtral. Muy generoso en su tier gratuito.
*   **Cerebras/Sambanova**: Alternativas de inferencia ultra-rápida (Llama 3.1).
*   **Ollama (Local)**: El "seguro de vida". Si el internet falla o todas las cuotas se agotan, se usa el hardware local (Llama 3, Phi-3).

---

## 2. 🧠 Memoria Semántica (RAG Local)
Actualmente usamos SQLite para historial de mensajes (Memoria de Corto Plazo).
*   **Mejora**: Integrar `ChromaDB` o `FAISS` (locales y gratis) para que el equipo pueda buscar en archivos de proyectos pasados "enterrados" en el historial.

---

## 3. 🚀 Ejecución Asíncrona de Agentes
Actualmente el flujo es lineal (`Manager -> Planner -> Builder`).
*   **Mejora**: Si el `Planner` define 3 tareas independientes, el `Manager` puede lanzar 3 `Builders` en paralelo (siempre que los Rate Limits lo permitan) para acelerar el desarrollo.

---

## 4. 🛡️ Sandbox de Seguridad Avanzado
*   **Mejora**: En lugar de solo filtrar comandos en `executor.py`, ejecutar el código de la IA dentro de un contenedor **Docker** temporal. Esto permite que la IA pruebe el código de forma real sin riesgo de romper el sistema operativo del usuario.

---

## 5. 🛠️ Sistema de Plugins para el Builder
Permitir que el Builder tenga "herramientas" predefinidas:
*   `search_web()`: Usando DuckDuckGo (Gratis).
*   `read_github_repo()`: Para clonar y entender otras bases de código.
*   `generate_image()`: Usando modelos estables gratuitos.
