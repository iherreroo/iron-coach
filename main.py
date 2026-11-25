"""Pregunta a Iron Coach desde la consola.

Uso:
    python main.py "Peso 80 kg, mido 180 cm, tengo 25 años. ¿Cuántas calorías para volumen?"
"""

import asyncio
import sys

from langchain_core.messages import HumanMessage

from app.grafo import construir_grafo


async def main() -> None:
    pregunta = " ".join(sys.argv[1:]) or input("Pregunta: ")
    grafo = await construir_grafo()
    entrada = {"messages": [HumanMessage(pregunta)], "hallazgos": [], "trazas": []}
    async for evento in grafo.astream(entrada, stream_mode="updates"):
        for nodo, cambios in evento.items():
            if nodo == "supervisor":
                print(f"[supervisor] -> {cambios['siguiente']}: {cambios['tarea']}")
            elif nodo == "responder":
                print("  [responder] borrador redactado")
            elif nodo == "verificar":
                for traza in cambios.get("trazas", []):
                    print(f"  [verificar] sin respaldo: {traza['sin_respaldo'] or 'nada'}")
                print("\n" + cambios["messages"][-1].text)
            else:
                for traza in cambios.get("trazas", []):
                    print(f"  [{nodo}] {traza['tipo']}: {traza['herramienta']}")


if __name__ == "__main__":
    asyncio.run(main())
