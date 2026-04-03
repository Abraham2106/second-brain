# Cambios y Motivos (Recap)

Este documento resume por qu se hicieron los cambios recientes en el proyecto y qu problema resuelven.

## 1) Problema: 429 RESOURCE_EXHAUSTED (cuota/ratelimit)
Se observaron errores `429 RESOURCE_EXHAUSTED` desde Gemini, incluyendo casos donde el mensaje indicaba `limit: 0`. Eso significa que la llave/proyecto no tena cuota disponible (o estaba agotada), por lo que reintentar con la misma configuracin no iba a funcionar.

Motivo del cambio:
Necesitbamos evitar que toda la app se quedara bloqueada cuando una llave o un modelo se agota temporalmente, y habilitar rotacin automtica a otras llaves/modelos cuando sea posible.

## 2) Load Balancer de API Keys + Modelos
Se agreg un balancer para rotar:

- Modelos (failover) cuando hay `429`
- Llaves (API keys) cuando los modelos de una llave estn agotados/en cooldown

Motivo del cambio:
Reducir errores por agotamiento y mantener el flujo multi-agente funcionando sin intervencin manual constante.

Notas:
- Rotar llaves solo ayuda si las llaves pertenecen a proyectos/planes con cuota diferente o cuota habilitada. Si todas comparten `limit: 0`, no hay balancer que lo arregle.

## 3) Reestructuracin del `.env`
Antes haba variables como `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2` e incluso una con espacios alrededor del `=`. El runtime no las lea, porque esperaba `GEMINI_API_KEY` o `GEMINI_API_KEYS`.

Se ajust para:
- Usar `GEMINI_API_KEYS="k1,k2,k3"` como fuente principal.
- Mantener compatibilidad con `GEMINI_API_KEY="k1"` si solo hay una.

Motivo del cambio:
Evitar configuracin "silenciosamente rota", donde la app corre pero no ve ninguna llave.

## 4) Clean Code: Configuracin y Logging centralizados
Se introdujo una configuracin central (`Settings`) y logging por sesin:

- Un solo lugar para cargar `.env` y validar settings.
- Logs por `task_id` para depurar qu pas y con qu agente/modelo/llave.

Motivo del cambio:
Eliminar `load_dotenv()` y `os.getenv()` dispersos, reducir efectos secundarios y facilitar diagnstico.

## 5) Clean Code: Contratos y manejo de errores
Se agregaron errores de dominio (por ejemplo `ConfigError`, errores de Gemini), y el orquestador fue endurecido para capturar fallos de agentes sin crashear de forma confusa.

Motivo del cambio:
Cuando hay fallos externos (API, cuota, red) es mejor tener errores claros y controlados, y logs tiles para rastrear qu ocurri.

## 6) `.gitignore` para vault personal y artefactos
Se ajust `.gitignore` para ignorar:

- `obsidian-vaults/Playground/` (vault personal)
- `.obsidian/` (settings del vault)
- `logs/` y `*.log`
- `.env`, `venv/`, `.workspace/`, `ai_team.db`, etc.

Motivo del cambio:
Evitar subir secretos, datos locales y tu vault personal al repositorio.

## 7) Problema: Wikilinks que "se ven" pero no funcionan
Se detect que varias notas tenan links como:

- `` `[[Nota]]` ``

Obsidian NO interpreta wikilinks dentro de inline-code (backticks) ni dentro de code fences, por lo que no son clickeables.

Se corrigi:
- Se actualiz el prompt del Builder para prohibir `[[...]]` dentro de backticks.
- Se actualiz el prompt del Critic para rechazar ese output.
- Se aplic una correccin automtica en el vault para convertir `` `[[...]]` `` a `[[...]]` en notas existentes.

Motivo del cambio:
Garantizar que los links realmente funcionen en Obsidian y no solo se vean bonitos.

## 8) Problema: Ejemplos y carpetas referenciadas no existan
Las notas mencionaban rutas como `[[lenguajes/logico/ejemplos/relaciones_familiares.pl]]` pero los archivos/carpetas no haban sido creados.

Se agreg:
- Soporte nuevo para crear "assets" dentro del vault (no solo `.md`) usando:
  - `# vault_asset: ruta/archivo.ext`
- Se generaron los archivos de ejemplo (Prolog/Python) y se crearon carpetas necesarias.

Motivo del cambio:
Hacer que los links apunten a contenido real y navegable, y no a referencias rotas.

## 9) Cambios en `main.py` por robustez
Se reescribi el arranque para:
- Inicializar settings una vez.
- Configurar logging por sesin.
- Evitar problemas de encoding que afectaban ejecucin/impresin.

Motivo del cambio:
Tener un entrypoint predecible, depurable y sin errores de encoding/side-effects.

