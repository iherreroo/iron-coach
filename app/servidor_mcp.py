"""Servidor MCP hecho con FastMCP: ofrece la búsqueda en ChromaDB como herramienta.

Lo puede usar cualquier cliente MCP: nuestro agente, Claude Code, Claude Desktop...
Normalmente lo arranca el cliente; para lanzarlo a mano:
    python -m app.servidor_mcp
"""

from fastmcp import FastMCP
from langchain_chroma import Chroma

from app.config import CARPETA_CHROMA, COLECCION, crear_embeddings

servidor = FastMCP("iron-coach-apuntes")

embeddings = crear_embeddings()
base = Chroma(
    collection_name=COLECCION,
    embedding_function=embeddings,
    persist_directory=str(CARPETA_CHROMA),
)

# Si la base está vacía (primer arranque), la creamos al vuelo
if base._collection.count() == 0:
    from app.ingesta import indexar

    indexar(base=base)


@servidor.tool
def buscar_apuntes(consulta: str, k: int = 4) -> str:
    """Busca en la base de conocimiento de culturismo: entrenamiento para hipertrofia,
    nutrición y macros, suplementos, recuperación y sueño, y ejercicios y rutinas.
    Devuelve los k fragmentos más parecidos a la consulta, con su fuente."""
    resultados = base.similarity_search(consulta, k=k)
    return "\n\n".join(
        f"[Fuente: {doc.metadata['fuente']}]\n{doc.page_content}" for doc in resultados
    )


if __name__ == "__main__":
    # stdio: el cliente habla con el servidor por la entrada y salida estándar
    servidor.run(transport="stdio", show_banner=False, log_level="WARNING")
