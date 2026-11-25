"""Herramientas locales del agente calculadora.

Cada herramienta es una función normal con el decorador @tool. El modelo lee el
docstring para saber cuándo usarla y los tipos para saber qué pasarle.
Las fórmulas viven en funciones puras (prefijo _) para poder probarlas sin LLM.
"""

from typing import Literal

from langchain_core.tools import tool

# --------------------------------------------------------------------------
# Fórmulas puras
# --------------------------------------------------------------------------


def _tmb(peso_kg: float, altura_cm: float, edad: int, sexo: str) -> float:
    """Mifflin-St Jeor: 10*peso + 6,25*altura - 5*edad + 5 (hombre) o -161 (mujer)."""
    constante = 5 if sexo == "hombre" else -161
    return round(10 * peso_kg + 6.25 * altura_cm - 5 * edad + constante, 1)


def _calorias_objetivo(tdee: float, objetivo: str, ajuste_kcal: float | None) -> float:
    por_defecto = {"volumen": 300, "definicion": -400, "mantenimiento": 0}
    if ajuste_kcal is None:
        ajuste = por_defecto[objetivo]
    else:  # el signo lo decide el objetivo, no el usuario
        ajuste = abs(ajuste_kcal) * (-1 if objetivo == "definicion" else 1)
        ajuste = 0 if objetivo == "mantenimiento" else ajuste
    return round(tdee + ajuste)


def _macros(peso_kg: float, calorias: float, objetivo: str) -> dict:
    proteina_g_kg = 2.2 if objetivo == "definicion" else 1.8
    grasa_g_kg = 0.9
    proteina_g = round(peso_kg * proteina_g_kg)
    grasa_g = round(peso_kg * grasa_g_kg)
    kcal_restantes = calorias - proteina_g * 4 - grasa_g * 9
    hidratos_g = max(0, round(kcal_restantes / 4))
    return {
        "calorias": round(calorias),
        "proteina_g": proteina_g,
        "grasa_g": grasa_g,
        "hidratos_g": hidratos_g,
        "proteina_g_por_kg": proteina_g_kg,
        "grasa_g_por_kg": grasa_g_kg,
    }


def _epley(peso_kg: float, repeticiones: int) -> float:
    if repeticiones == 1:
        return round(peso_kg, 1)
    return round(peso_kg * (1 + repeticiones / 30), 1)


def _discos(peso_total_kg: float, peso_barra_kg: float) -> dict:
    por_lado = (peso_total_kg - peso_barra_kg) / 2
    if por_lado < 0:
        return {"error": "El peso total es menor que el peso de la barra."}
    restante = por_lado
    discos: list[float] = []
    for disco in (25, 20, 15, 10, 5, 2.5, 1.25):
        while restante + 1e-9 >= disco:
            discos.append(disco)
            restante = round(restante - disco, 2)
    return {
        "discos_por_lado_kg": discos,
        "peso_conseguido_kg": round(peso_barra_kg + 2 * sum(discos), 2),
        "sobrante_por_lado_kg": round(restante, 2),
    }


# --------------------------------------------------------------------------
# Herramientas que ve el LLM
# --------------------------------------------------------------------------


@tool
def calcular_tmb(
    peso_kg: float, altura_cm: float, edad: int, sexo: Literal["hombre", "mujer"]
) -> float:
    """Calcula la tasa metabólica basal (kcal/día en reposo) con la ecuación
    de Mifflin-St Jeor."""
    return _tmb(peso_kg, altura_cm, edad, sexo)


@tool
def calcular_tdee(tmb: float, dias_entrenamiento_semana: int) -> dict:
    """Calcula el gasto energético total diario (kcal de mantenimiento) a partir de
    la TMB y de los días de entrenamiento por semana (0 a 7)."""
    if dias_entrenamiento_semana <= 1:
        factor = 1.2
    elif dias_entrenamiento_semana <= 3:
        factor = 1.375
    elif dias_entrenamiento_semana <= 5:
        factor = 1.55
    else:
        factor = 1.725
    return {"tdee_kcal": round(tmb * factor), "factor_actividad": factor}


@tool
def calcular_calorias_objetivo(
    tdee: float,
    objetivo: Literal["volumen", "definicion", "mantenimiento"],
    ajuste_kcal: float | None = None,
) -> float:
    """Calcula las calorías diarias según el objetivo. Si no se indica ajuste_kcal,
    usa +300 kcal para volumen y -400 kcal para definición."""
    return _calorias_objetivo(tdee, objetivo, ajuste_kcal)


@tool
def calcular_macros(
    peso_kg: float,
    calorias: float,
    objetivo: Literal["volumen", "definicion", "mantenimiento"],
) -> dict:
    """Reparte las calorías en proteína, grasa e hidratos (gramos al día).
    Proteína 1,8 g/kg (2,2 g/kg en definición) y grasa 0,9 g/kg; el resto, hidratos."""
    return _macros(peso_kg, calorias, objetivo)


@tool
def estimar_1rm(peso_kg: float, repeticiones: int) -> float:
    """Estima el 1RM (máximo para una repetición) con la fórmula de Epley a partir de
    una serie de 1 a 12 repeticiones."""
    return _epley(peso_kg, repeticiones)


@tool
def calcular_discos(peso_total_kg: float, peso_barra_kg: float = 20.0) -> dict:
    """Calcula qué discos poner a cada lado de la barra para llegar a un peso total."""
    return _discos(peso_total_kg, peso_barra_kg)


HERRAMIENTAS_CALCULADORA = [
    calcular_tmb,
    calcular_tdee,
    calcular_calorias_objetivo,
    calcular_macros,
    estimar_1rm,
    calcular_discos,
]
