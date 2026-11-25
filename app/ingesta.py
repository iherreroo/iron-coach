"""Ingesta RAG: lee los documentos, los trocea y los guarda en ChromaDB.

Se ejecuta una vez, y otra cada vez que cambien los documentos:
    python -m app.ingesta
"""

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CARPETA_CHROMA, CARPETA_DOCS, COLECCION, crear_embeddings


def cargar_documentos() -> list[Document]:
    """Lee cada .md de conocimiento/ como un Document (texto + metadatos)."""
    documentos = []
    for fichero in sorted(CARPETA_DOCS.glob("*.md")):
        texto = fichero.read_text(encoding="utf-8")
        documentos.append(Document(page_content=texto, metadata={"fuente": fichero.name}))
    return documentos


def trocear(documentos: list[Document]) -> list[Document]:
    """Parte los documentos en fragmentos (chunks) de unos 500 caracteres.

    Se corta primero por apartados (##), después por párrafos y frases.
    chunk_overlap repite 50 caracteres entre fragmentos para no cortar ideas.
    """
    troceador = RecursiveCharacterTextSplitter(
        chunk_size=500, chunk_overlap=50, separators=["\n## ", "\n\n", "\n", ". ", " "]
    )
    return troceador.split_documents(documentos)  # heredan los metadatos


def indexar(embeddings=None, base=None) -> int:
    """Calcula el vector de cada fragmento y lo guarda en ChromaDB (en disco)."""
    fragmentos = trocear(cargar_documentos())
    if base is None:
        base = Chroma(
            collection_name=COLECCION,
            embedding_function=embeddings or crear_embeddings(),
            persist_directory=str(CARPETA_CHROMA),
        )
    # Identificadores fijos: al repetir la ingesta se sobrescriben, no se duplican
    ids = [f"{f.metadata['fuente']}-{i}" for i, f in enumerate(fragmentos)]
    base.add_documents(fragmentos, ids=ids)
    return len(fragmentos)


if __name__ == "__main__":
    total = indexar()
    print(f"Guardados {total} fragmentos en {CARPETA_CHROMA}")
