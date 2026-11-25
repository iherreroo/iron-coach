"""Agentes especialistas.

Agente = modelo + instrucciones (system prompt) + herramientas.
create_agent monta el bucle: pensar -> usar herramienta -> leer resultado -> responder.
"""

import sys

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import RAIZ
from app.herramientas import HERRAMIENTAS_CALCULADORA

CONFIG_SERVIDOR_MCP = {
    "apuntes": {
        "transport": "stdio",
        "command": sys.executable,  # el mismo Python que ejecuta este programa
        "args": ["-m", "app.servidor_mcp"],
        "cwd": str(RAIZ),
    }
}


def crear_cliente_mcp() -> MultiServerMCPClient:
    """Cliente que lanza nuestro servidor MCP como subproceso (stdio)."""
    return MultiServerMCPClient(CONFIG_SERVIDOR_MCP)


async def cargar_herramientas_mcp() -> list:
    """Arranca el servidor MCP y convierte sus herramientas al formato LangChain.

    Cada llamada a una herramienta lanza un proceso nuevo. Para una app que
    queda abierta (server.py) se usa una sesión persistente.
    """
    return await crear_cliente_mcp().get_tools()


async def crear_especialistas(modelo, herramientas_mcp=None) -> dict:
    """Devuelve un diccionario {nombre: agente}."""
    if herramientas_mcp is None:
        herramientas_mcp = await cargar_herramientas_mcp()

    documentalista = create_agent(
        modelo,
        tools=herramientas_mcp,  # buscar_apuntes, que llega desde el servidor MCP
        system_prompt=(
            "Eres el documentalista de Iron Coach, un asistente de culturismo. "
            "Busca SIEMPRE con tu herramienta buscar_apuntes antes de responder. "
            "Responde SOLO con lo que digan literalmente los fragmentos recuperados, "
            "copiando las cifras tal cual y citando el fichero de la fuente. "
            "Está PROHIBIDO añadir nada de tu propio conocimiento: ni suplementos, "
            "ni dosis, ni consejos, ni cifras que no aparezcan en los fragmentos. "
            "Si lo que piden no está en los documentos, di exactamente: "
            "'Eso no está en mi base de conocimiento'. "
            "Sé conciso: máximo 120 palabras."
        ),
        name="documentalista",
    )
    calculadora = create_agent(
        modelo,
        tools=HERRAMIENTAS_CALCULADORA,
        system_prompt=(
            "Eres la calculadora de Iron Coach. Haz las cuentas SIEMPRE con tus "
            "herramientas, nunca de cabeza: llama a una herramienta por cada cosa que "
            "te pidan (1RM -> estimar_1rm; discos o carga de la barra -> calcular_discos). "
            "Para un plan de calorías encadena: "
            "calcular_tmb, calcular_tdee, calcular_calorias_objetivo y calcular_macros. "
            "Antes de responder, comprueba que has llamado a la herramienta de CADA "
            "cálculo pedido; si falta alguno, llámala. Explica el resultado en pocas "
            "líneas con los números que devolvieron las herramientas. Solo haces "
            "cálculos: si te piden teoría, suplementos o recomendaciones, ignóralo, "
            "porque de eso se encarga otro especialista."
        ),
        name="calculadora",
    )
    return {"documentalista": documentalista, "calculadora": calculadora}
