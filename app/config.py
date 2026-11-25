"""Configuración común: rutas, modelo de lenguaje y modelo de embeddings."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.embeddings import Embeddings

# Lee las variables del fichero .env (por ejemplo, GROQ_API_KEY)
load_dotenv()

RAIZ = Path(__file__).parent.parent
CARPETA_DOCS = RAIZ / "conocimiento"  # documentos de los que aprende el RAG
CARPETA_CHROMA = RAIZ / "chroma_db"   # donde ChromaDB guarda la base vectorial
COLECCION = "iron_coach"

# Modelo de embeddings multilingüe que se ejecuta en local (gratis, sin clave)
MODELO_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def crear_modelo(ligero: bool = False):
    """Modelo de lenguaje (LLM) en el plan gratuito de Groq (Llama 3.3 ya no está disponible).

    - Principal (agentes y respuesta): variable MODELO, por defecto qwen3.8-27b.
    - Ligero (solo el verificador): variable MODELO_LIGERO, por defecto gpt-oss-20b.

    Groq limita los tokens por minuto de cada modelo por separado, así que repartir
    el trabajo entre dos modelos duplica la capacidad. max_retries hace que, si se
    alcanza el límite, se espere y se reintente en vez de fallar.
    """
    if ligero:
        nombre = os.getenv("MODELO_LIGERO", "groq:openai/gpt-oss-20b")
    else:
        nombre = os.getenv("MODELO", "groq:qwen/qwen3.8-27b")
    return init_chat_model(nombre, temperature=0, max_retries=6)


class EmbeddingsLocales(Embeddings):
    """Convierte textos en vectores con fastembed y los adapta a LangChain."""

    _modelo = None

    @property
    def modelo(self):
        """Carga el modelo la primera vez que se usa (carga diferida).

        Importa: en algunas máquinas Windows, ChromaDB se cae si onnxruntime ya está
        cargado antes de crear su cliente. Con la carga diferida, el cliente de
        ChromaDB (que se crea en el constructor de Chroma) siempre va primero.
        """
        if self._modelo is None:
            from fastembed import TextEmbedding

            # La primera vez descarga el modelo (unos 220 MB) y lo guarda en caché
            self._modelo = TextEmbedding(MODELO_EMBEDDINGS)
        return self._modelo

    def embed_documents(self, textos: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self.modelo.embed(textos)]

    def embed_query(self, texto: str) -> list[float]:
        return self.embed_documents([texto])[0]


def crear_embeddings() -> Embeddings:
    return EmbeddingsLocales()
