"""Servidor web de Iron Coach: API de chat (con trazas en streaming) + frontend estático.

Arranque:
    python server.py            ->  http://localhost:8000
"""

import asyncio
import json
import os
import time
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from langchain_mcp_adapters.tools import load_mcp_tools
from pydantic import BaseModel, Field

from app.agentes import crear_cliente_mcp
from app.grafo import construir_grafo

WEB = Path(__file__).parent / "web"

# Protección del plan gratuito de Groq: límite por IP y peticiones simultáneas
MAX_PETICIONES = int(os.getenv("MAX_PETICIONES", "20"))  # por IP y ventana
VENTANA_SEGUNDOS = 600
MAX_SIMULTANEAS = 1  # el límite de Groq son tokens por minuto: mejor de una en una
peticiones: dict[str, deque] = defaultdict(deque)
semaforo = asyncio.Semaphore(MAX_SIMULTANEAS)

# Caché de preguntas repetidas (p. ej. las sugerencias de la web): se responden al
# instante y sin gastar cuota de Groq. Solo se cachean conversaciones sin historial.
CACHE_MAX = 100
cache: OrderedDict[str, list[str]] = OrderedDict()


def _normalizar(texto: str) -> str:
    return " ".join(texto.lower().split())


def _sembrar_cache() -> int:
    """Carga las conversaciones grabadas (web/demo.json) como respuestas ya cacheadas.

    Así las preguntas sugeridas se responden al instante aunque Groq no tenga cuota
    (p. ej. tras reiniciar el servidor o agotar el límite diario).
    """
    fichero = WEB / "demo.json"
    if not fichero.exists():
        return 0
    for caso in json.loads(fichero.read_text(encoding="utf-8")):
        lineas = [_linea(e) for e in caso["eventos"]] + [_linea({"tipo": "fin"})]
        cache[_normalizar(caso["pregunta"])] = lineas
    return len(cache)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.grafo = None
    app.state.error = None
    # CACHE_INICIAL=0 desactiva la siembra (necesario para regrabar la demo con grabar_demo.py)
    if os.getenv("CACHE_INICIAL", "1") != "0":
        _sembrar_cache()
    # Sesión MCP persistente: el servidor de búsqueda se arranca una sola vez
    async with crear_cliente_mcp().session("apuntes") as sesion:
        herramientas = await load_mcp_tools(sesion)
        try:
            app.state.grafo = await construir_grafo(herramientas_mcp=herramientas)
        except Exception as e:  # p. ej. falta GROQ_API_KEY
            app.state.error = f"No se pudo crear el modelo: {e}"
        yield


app = FastAPI(title="Iron Coach", lifespan=lifespan)


class Turno(BaseModel):
    rol: str  # "usuario" | "asistente"
    texto: str = Field(max_length=2000)


class Consulta(BaseModel):
    mensaje: str = Field(min_length=1, max_length=600)
    historial: list[Turno] = Field(default_factory=list, max_length=12)


def _ip(request: Request) -> str:
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


def _limitado(ip: str) -> bool:
    ahora = time.time()
    cola = peticiones[ip]
    while cola and ahora - cola[0] > VENTANA_SEGUNDOS:
        cola.popleft()
    if len(cola) >= MAX_PETICIONES:
        return True
    cola.append(ahora)
    return False


def _linea(evento: dict) -> str:
    return json.dumps(evento, ensure_ascii=False) + "\n"


async def _reproducir(lineas: list[str]):
    """Reproduce una conversación guardada con pequeñas pausas, como si fuera en vivo."""
    for linea in lineas:
        yield linea
        await asyncio.sleep(0.35)


def _mensaje_error(e: Exception) -> str:
    texto = str(e)
    if "rate_limit" in texto.lower() or "429" in texto:
        return "Groq está saturado en este momento (límite del plan gratuito). Prueba de nuevo en un minuto."
    return f"Error inesperado: {texto[:200]}"


@app.get("/api/health")
async def salud():
    return {"ok": app.state.grafo is not None, "error": app.state.error}


@app.post("/api/chat")
async def chat(consulta: Consulta, request: Request):
    if app.state.grafo is None:
        return JSONResponse({"error": app.state.error or "Iniciando..."}, status_code=503)
    clave = None if consulta.historial else _normalizar(consulta.mensaje)
    if clave in cache:  # repetida: se reproduce sin gastar cuota ni límite por IP
        cache.move_to_end(clave)
        return StreamingResponse(_reproducir(cache[clave]), media_type="application/x-ndjson")
    if _limitado(_ip(request)):
        return JSONResponse(
            {"error": "Demasiadas preguntas seguidas. Espera unos minutos."}, status_code=429
        )

    mensajes = [
        HumanMessage(t.texto) if t.rol == "usuario" else AIMessage(t.texto)
        for t in consulta.historial[-6:]
    ]
    mensajes.append(HumanMessage(consulta.mensaje))
    entrada = {"messages": mensajes, "hallazgos": [], "trazas": []}

    async def flujo():
        emitidas: list[str] = []
        async for linea in generar():
            emitidas.append(linea)
            yield linea
        if clave and emitidas and json.loads(emitidas[-1])["tipo"] == "fin":
            cache[clave] = emitidas
            while len(cache) > CACHE_MAX:
                cache.popitem(last=False)

    async def generar():
        async with semaforo:
            try:
                yield _linea({"tipo": "inicio"})
                async for evento in app.state.grafo.astream(entrada, stream_mode="updates"):
                    for nodo, cambios in evento.items():
                        if nodo == "supervisor":
                            yield _linea(
                                {
                                    "tipo": "supervisor",
                                    "siguiente": cambios["siguiente"],
                                    "tarea": cambios["tarea"],
                                }
                            )
                        elif nodo == "responder":
                            yield _linea({"tipo": "redactado"})
                        elif nodo == "verificar":
                            for traza in cambios.get("trazas", []):
                                yield _linea(traza)
                            yield _linea(
                                {"tipo": "respuesta", "texto": str(cambios["messages"][-1].text)}
                            )
                        else:
                            for traza in cambios.get("trazas", []):
                                yield _linea(traza)
                yield _linea({"tipo": "fin"})
            except Exception as e:
                yield _linea({"tipo": "error", "mensaje": _mensaje_error(e)})

    return StreamingResponse(flujo(), media_type="application/x-ndjson")


# El frontend se sirve en la raíz (debe ir después de las rutas /api)
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
