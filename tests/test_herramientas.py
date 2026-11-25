"""Pruebas de las fórmulas de la calculadora (no necesitan LLM ni clave).

    python -m unittest discover -s tests
"""

import unittest

from app.herramientas import (
    _calorias_objetivo,
    _discos,
    _epley,
    _macros,
    _tmb,
    calcular_tdee,
)


class TestFormulas(unittest.TestCase):
    def test_tmb_hombre(self):
        # 10*80 + 6.25*180 - 5*25 + 5 = 1805
        self.assertEqual(_tmb(80, 180, 25, "hombre"), 1805.0)

    def test_tmb_mujer(self):
        # 10*60 + 6.25*165 - 5*30 - 161 = 1320.25
        self.assertAlmostEqual(_tmb(60, 165, 30, "mujer"), 1320.2, places=1)

    def test_tdee(self):
        res = calcular_tdee.invoke({"tmb": 1800, "dias_entrenamiento_semana": 4})
        self.assertEqual(res["factor_actividad"], 1.55)
        self.assertEqual(res["tdee_kcal"], 2790)

    def test_calorias_objetivo(self):
        self.assertEqual(_calorias_objetivo(2800, "volumen", None), 3100)
        self.assertEqual(_calorias_objetivo(2800, "definicion", None), 2400)
        self.assertEqual(_calorias_objetivo(2800, "definicion", 500), 2300)
        self.assertEqual(_calorias_objetivo(2800, "mantenimiento", 500), 2800)

    def test_macros_suman_calorias(self):
        m = _macros(80, 3000, "volumen")
        total = m["proteina_g"] * 4 + m["grasa_g"] * 9 + m["hidratos_g"] * 4
        self.assertAlmostEqual(total, 3000, delta=4)
        self.assertEqual(m["proteina_g"], 144)  # 1,8 g/kg

    def test_epley(self):
        self.assertEqual(_epley(100, 1), 100.0)
        self.assertEqual(_epley(100, 5), 116.7)

    def test_discos(self):
        r = _discos(100, 20)  # 40 kg por lado = 25 + 15
        self.assertEqual(r["discos_por_lado_kg"], [25, 15])
        self.assertEqual(r["peso_conseguido_kg"], 100.0)
        self.assertIn("error", _discos(10, 20))


if __name__ == "__main__":
    unittest.main()
