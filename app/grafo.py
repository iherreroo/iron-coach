"""Orquestación con LangGraph: un supervisor reparte el trabajo entre especialistas.

INICIO -> supervisor -> (documentalista | calculadora) -> supervisor -> ...
             -> responder -> verificar -> FIN
"""

import operator
import re
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel, Field, create_model

from app.agentes import crear_especialistas
from app.config import crear_modelo

MAX_PASOS = 4  # límite de seguridad para que el supervisor no entre en bucle


class Estado(MessagesState):
    """Estado compartido del grafo. La clave "messages" ya viene de MessagesState."""

    siguiente: str  # a quién le toca actuar
    tarea: str  # encargo para ese especialista
    hallazgos: Annotated[list[str], operator.add]  # se acumulan, no se sustituyen
    trazas: Annotated[list[dict], operator.add]  # lo que hicieron los agentes (para la web)
    borrador: str  # respuesta previa a la verificación


def _esquema_decision(opciones: list[str]) -> type[BaseModel]:
    """Esquema de Decision restringido a las opciones que siguen disponibles."""
    return create_model(
        "Decision",
        __doc__="Respuesta estructurada del supervisor.",
        siguiente=(
            Literal[tuple(opciones)],  # type: ignore[valid-type]
            Field(description="Quién actúa ahora, o FIN si ya hay información suficiente."),
        ),
        tarea=(str, Field(description="Encargo completo, con los datos. Vacío si FIN.")),
    )


PROMPT_SUPERVISOR = """Eres el supervisor de Iron Coach, un asistente de culturismo.
No respondes al usuario: decides qué especialista actúa.

- documentalista: busca en la base de conocimiento (entrenamiento para hipertrofia,
  nutrición y macros, suplementos, recuperación y sueño, ejercicios y rutinas).
- calculadora: hace cálculos (TMB, TDEE, calorías objetivo, macros, 1RM estimado,
  discos de la barra).

Reglas (en este orden):
1. Si la pregunta NO es de entrenamiento, nutrición o suplementación: FIN.
2. Si "Información recogida" está vacía y la pregunta es de culturismo, NUNCA
   respondas FIN (salvo en la regla 3): tú no sabes nada, hay que consultar a un
   especialista. Eso incluye preguntas que mezclan cálculo y teoría.
3. Datos imprescindibles de cada cálculo:
   - plan de calorías o macros: peso, altura, edad, sexo, días de entrenamiento por
     semana y objetivo (volumen, definición o mantenimiento);
   - 1RM: peso levantado y repeticiones; discos de la barra: peso total.
   Si falta alguno de ellos y el usuario no lo ha dado, responde FIN (la respuesta
   le pedirá SOLO lo que falte). Si están todos, NO pidas nada más: calcula.
4. Teoría, recomendaciones o dudas: documentalista.
5. Números: calculadora. Pásale TODOS los datos en la tarea (peso, altura, edad,
   sexo, días de entrenamiento, objetivo...).
6. La tarea de cada especialista incluye SOLO lo suyo: a la calculadora, únicamente
   los cálculos; al documentalista, únicamente las dudas de teoría, suplementos,
   estudios o recomendaciones. Nunca copies la pregunta entera a uno solo.
7. Si la pregunta pide cálculo Y teoría, usa los dos, de uno en uno. Cada
   especialista se usa como mucho una vez. Cuando ya hayan actuado todos los que
   la pregunta necesita: FIN.

Información recogida hasta ahora:
{hallazgos}"""

PROMPT_RESPUESTA = """Eres Iron Coach, un asistente de culturismo directo y motivador.
Responde en español, con claridad y sin rodeos, usando SOLO esta información.
Cita el fichero de origen entre paréntesis, por ejemplo (nutricion_macros.md), cuando
venga de los documentos. No uses marcas como 【】.

{hallazgos}

Reglas:
- Prohibido inventar categorías, objetivos o rangos (por ejemplo "para fuerza" o
  "para definición") que no aparezcan escritos arriba. Copia las cifras tal cual.
- Cada frase debe poder apoyarse en la información de arriba. No añadas datos,
  efectos secundarios, estudios ni cifras que no estén escritos ahí, aunque los
  conozcas. Si la pregunta pedía algo que ningún especialista aportó, dilo.
- Los números de calorías y macros vienen de la calculadora; la teoría y las
  recomendaciones, del documentalista. No los mezcles.
- Si la información de arriba dice "Ninguna todavía", NO respondas con tu propio
  conocimiento: pide los datos que falten o explica que no tienes información.
- Si no hay información suficiente, dilo y pide SOLO los datos que falten
  (para calorías y macros: peso, altura, edad, sexo, días de entrenamiento por
  semana y objetivo; para el 1RM: peso y repeticiones). No pidas nada más.
- Si la pregunta no tiene que ver con entrenamiento, nutrición o suplementación,
  explica amablemente que solo puedes ayudar con eso.
- Si hablas de salud, lesiones, dolor o enfermedades, recuerda que no sustituyes a
  un médico. No recomiendes esteroides ni sustancias dopantes.
- Usa listas cortas y negritas para los números clave. Máximo 200 palabras."""


class Verificacion(BaseModel):
    """Resultado de contrastar el borrador con la información recogida."""

    # Con valores por defecto: si el modelo omite un campo, no es un error de validación
    sin_respaldo: list[str] = Field(
        default_factory=list,
        description="Frases o datos del borrador que NO están respaldados por la información. "
        "Lista vacía si todo está respaldado.",
    )
    respuesta_final: str = Field(
        default="",
        description="El borrador sin lo que no tenga respaldo (mismo formato y tono). "
        "Si todo estaba respaldado, el borrador tal cual.",
    )


PROMPT_VERIFICADOR = """Eres el verificador de Iron Coach. Compruebas que un borrador de
respuesta solo diga cosas respaldadas por la información recogida.

INFORMACIÓN RECOGIDA:
{hallazgos}

BORRADOR:
{borrador}

Busca en el borrador datos, cifras, dosis, suplementos, estudios, rangos o consejos que
NO aparezcan en la información recogida (aunque sean ciertos en la vida real).
Sí son válidos y no hay que quitarlos:
- cálculos derivados directamente de las cifras de la información (porcentajes, sumas);
- frases de cortesía o ánimo, y la recomendación de acudir a un médico o profesional;
- peticiones al usuario de los datos que faltan.
Si hay algo sin respaldo, lístalo y devuelve respuesta_final sin eso (si al quitarlo
queda una frase incompleta, reescríbela o bórrala). Si no hay nada, lista vacía."""


# Errores 400 ocasionales de Groq cuando el modelo genera una llamada a herramienta o un
# JSON mal formado. No son del código: repetir la llamada suele bastar.
_ERRORES_REINTENTABLES = ("Parsing failed", "failed_generation", "tool_use_failed", "validation")


def _es_reintentable(error: Exception) -> bool:
    return any(marca in str(error) for marca in _ERRORES_REINTENTABLES)


async def _reintentar(operacion, intentos: int = 3):
    """Ejecuta `operacion()` (una corrutina) y la repite si falla con un error reintentable."""
    for n in range(intentos):
        try:
            return await operacion()
        except Exception as e:
            if n == intentos - 1 or not _es_reintentable(e):
                raise


def _texto(estado: Estado) -> str:
    return "\n".join(estado.get("hallazgos", [])) or "Ninguna todavía."


def _contenido(mensaje) -> str:
    """Texto de un mensaje, sea cual sea la forma en la que lo guarde LangChain."""
    return str(mensaje.text)


def _extraer_trazas(nombre: str, mensajes: list) -> list[dict]:
    """Convierte la conversación interna de un agente en eventos para la interfaz."""
    trazas = []
    for m in mensajes:
        for llamada in getattr(m, "tool_calls", None) or []:
            trazas.append(
                {
                    "tipo": "herramienta",
                    "agente": nombre,
                    "herramienta": llamada["name"],
                    "args": llamada["args"],
                }
            )
        if m.type == "tool":
            contenido = _contenido(m)
            fuentes = sorted(set(re.findall(r"\[Fuente: ([^\]]+)\]", contenido)))
            trazas.append(
                {
                    "tipo": "resultado",
                    "agente": nombre,
                    "herramienta": m.name,
                    "resultado": contenido[:600],
                    "fuentes": fuentes,
                }
            )
    return trazas


async def construir_grafo(modelo=None, herramientas_mcp=None, modelo_ligero=None):
    """modelo: supervisor, agentes y respuesta. modelo_ligero: solo el verificador."""
    ligero = modelo_ligero or (modelo if modelo is not None else crear_modelo(ligero=True))
    modelo = modelo or crear_modelo()
    especialistas = await crear_especialistas(modelo, herramientas_mcp)
    # --- Nodos: reciben el estado y devuelven solo lo que cambian ---

    async def supervisor(estado: Estado) -> dict:
        hallazgos = estado.get("hallazgos", [])
        if len(hallazgos) >= MAX_PASOS:
            return {"siguiente": "FIN", "tarea": ""}
        # Un especialista que ya actuó deja de ser una opción: así el supervisor no
        # puede repetirlo y se ve obligado a usar al otro o a terminar.
        ya_actuaron = {h[1 : h.index("]")] for h in hallazgos}
        disponibles = [n for n in especialistas if n not in ya_actuaron]
        opciones = disponibles + ["FIN"]
        # El enrutado es la decisión más delicada del sistema: usa el modelo principal
        decisor = modelo.with_structured_output(_esquema_decision(opciones))
        prompt = PROMPT_SUPERVISOR.format(hallazgos=_texto(estado))
        if ya_actuaron:
            prompt += (
                f"\n\nYa han actuado: {', '.join(sorted(ya_actuaron))} (no pueden repetir). "
                f"Opciones ahora: {', '.join(opciones)}. Si la pregunta pedía algo que "
                "todavía no está cubierto (estudios, recomendaciones, teoría, cálculos) "
                "y queda un especialista que puede aportarlo, llámalo; si no, FIN."
            )
        mensajes = [SystemMessage(prompt), *estado["messages"]]
        segunda_opinion = False
        for intento in range(3):
            try:
                decision = await decisor.ainvoke(mensajes)
                if decision.siguiente == "FIN" and not hallazgos and not segunda_opinion:
                    # Terminar sin haber consultado a nadie es lo más caro de equivocar
                    # (la respuesta saldría vacía): se pide una segunda opinión.
                    segunda_opinion = True
                    mensajes = [
                        *mensajes,
                        HumanMessage(
                            "Aún no has consultado a ningún especialista. Revisa las reglas: "
                            "si la pregunta es de entrenamiento, nutrición o suplementación y "
                            "NO faltan datos imprescindibles (peso y repeticiones bastan para "
                            "el 1RM; el peso total basta para los discos), elige un especialista "
                            "y redacta su tarea. Solo mantén FIN si de verdad falta un dato "
                            "imprescindible o la pregunta no es del tema."
                        ),
                    ]
                    continue
                return {"siguiente": decision.siguiente, "tarea": decision.tarea}
            except Exception as e:
                # Groq rechaza respuestas que no cumplen el esquema (tool_use_failed)
                if not _es_reintentable(e):
                    raise
                mensajes = [
                    *mensajes,
                    HumanMessage(f"Responde eligiendo SOLO entre: {', '.join(opciones)}."),
                ]
        return {"siguiente": "FIN", "tarea": ""}

    def crear_nodo(nombre: str):
        async def nodo(estado: Estado) -> dict:
            # El especialista solo recibe su encargo, no toda la conversación
            entrada = {"messages": [HumanMessage(estado["tarea"])]}
            resultado = await _reintentar(lambda: especialistas[nombre].ainvoke(entrada))
            return {
                "hallazgos": [f"[{nombre}] {_contenido(resultado['messages'][-1])}"],
                "trazas": _extraer_trazas(nombre, resultado["messages"]),
            }

        return nodo

    async def responder(estado: Estado) -> dict:
        prompt = PROMPT_RESPUESTA.format(hallazgos=_texto(estado))
        respuesta = await _reintentar(
            lambda: modelo.ainvoke([SystemMessage(prompt), *estado["messages"]])
        )
        # gpt-oss añade marcas de cita 【...】 propias: se quitan, citamos ficheros
        limpio = re.sub(r"\s*【[^】]*】", "", _contenido(respuesta))
        return {"borrador": limpio}

    verificador = ligero.with_structured_output(Verificacion)

    async def verificar(estado: Estado) -> dict:
        """Comprueba que el borrador solo diga cosas respaldadas por la información."""
        borrador = estado["borrador"]
        if not estado.get("hallazgos"):  # no hay nada que contrastar (faltan datos, etc.)
            traza = {"tipo": "verificacion", "sin_respaldo": [], "omitida": True}
            return {"messages": [AIMessage(borrador)], "trazas": [traza]}
        prompt = PROMPT_VERIFICADOR.format(hallazgos=_texto(estado), borrador=borrador)
        try:
            veredicto = await _reintentar(lambda: verificador.ainvoke([SystemMessage(prompt)]))
        except Exception as e:
            if not _es_reintentable(e):
                raise
            # El verificador falló del todo: se entrega el borrador, avisando de que no se verificó
            traza = {"tipo": "verificacion", "sin_respaldo": [], "omitida": False, "fallida": True}
            return {"messages": [AIMessage(borrador)], "trazas": [traza]}
        sin_respaldo = [a for a in veredicto.sin_respaldo if a.strip()]
        final = veredicto.respuesta_final.strip() if sin_respaldo else borrador
        traza = {"tipo": "verificacion", "sin_respaldo": sin_respaldo, "omitida": False}
        return {"messages": [AIMessage(final or borrador)], "trazas": [traza]}

    # --- Grafo: nodos y aristas ---

    grafo = StateGraph(Estado)
    grafo.add_node("supervisor", supervisor)
    grafo.add_node("responder", responder)
    grafo.add_node("verificar", verificar)
    for nombre in especialistas:
        grafo.add_node(nombre, crear_nodo(nombre))
        grafo.add_edge(nombre, "supervisor")  # cada especialista vuelve al supervisor

    grafo.add_edge(START, "supervisor")
    # Arista condicional: el destino depende de estado["siguiente"]
    rutas = {"documentalista": "documentalista", "calculadora": "calculadora", "FIN": "responder"}
    grafo.add_conditional_edges("supervisor", lambda estado: estado["siguiente"], rutas)
    grafo.add_edge("responder", "verificar")
    grafo.add_edge("verificar", END)
    return grafo.compile()
