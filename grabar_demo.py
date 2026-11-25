"""Graba conversaciones REALES contra el servidor y las guarda como demo para la web.

Con el servidor en marcha (python server.py), en otra terminal:
    python grabar_demo.py                    # escribe web/demo.json
    python grabar_demo.py salida.json        # o en otro fichero

Cada pregunta se envía a /api/chat y se guardan todos los eventos (supervisor,
herramientas, resultados y respuesta) tal y como los emitió el sistema.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://localhost:8000/api/chat"

# Son las mismas que las sugerencias de la web (web/app.js): así, al pulsarlas,
# el servidor responde con la grabación y no gasta cuota del LLM.
PREGUNTAS = [
    "Soy hombre, peso 80 kg, mido 180 cm y tengo 25 años. Entreno 4 días a la semana. ¿Cuántas calorías y macros necesito para ganar músculo?",
    "¿Cuántas series por semana necesito para el pecho y cuánto debo descansar entre series?",
    "Hago 100 kg x 5 repeticiones en press banca. ¿Cuál es mi 1RM estimado y qué discos pongo para 100 kg?",
    "¿Cuánta creatina tengo que tomar y hace falta hacer fase de carga?",
    "Llevo 3 semanas durmiendo mal y no progreso. ¿Qué hago?",
]


def grabar(pregunta: str) -> list[dict]:
    peticion = urllib.request.Request(
        URL,
        data=json.dumps({"mensaje": pregunta}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    eventos = []
    with urllib.request.urlopen(peticion, timeout=180) as respuesta:
        for linea in respuesta:
            evento = json.loads(linea)
            if evento["tipo"] == "error":
                raise RuntimeError(evento["mensaje"])
            if evento["tipo"] != "fin":
                eventos.append(evento)
    return eventos


def main() -> None:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "web" / "demo.json"
    demo = []
    for pregunta in PREGUNTAS:
        print("Grabando:", pregunta)
        for intento in range(1, 4):  # un fallo puntual del modelo no debe abortar la grabación
            try:
                eventos = grabar(pregunta)
                if any(e.get("fallida") for e in eventos):
                    raise RuntimeError("la verificación falló; se descarta esta grabación")
                break
            except RuntimeError as e:
                print(f"  intento {intento} fallido: {str(e)[:120]}")
                if intento == 3:
                    raise
                time.sleep(20)
        demo.append({"pregunta": pregunta, "eventos": eventos})
    destino.write_text(json.dumps(demo, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Guardado en", destino)


if __name__ == "__main__":
    main()
