"""
Pojistné zaměstnance a zaměstnavatele z vyměřovacího základu (rok 2026).

- Sociální pojištění (zákon č. 589/1992 Sb., § 7): zaměstnanec 7,1 %, zaměstnavatel 24,8 %;
  pojistné se zaokrouhluje na celé koruny nahoru.
- Zdravotní pojištění (zákon č. 592/1992 Sb., § 2): 13,5 % zaokrouhlené na celé koruny
  nahoru za každého zaměstnance zvlášť; zaměstnanec hradí třetinu této částky (zaokrouhlenou
  na koruny nahoru), zaměstnavatel zbytek. 4,5 % a 9 % se samostatně nezaokrouhlují.

Počítá se v Decimal – v binárních desetinných číslech by např. 32 000 × 0,071 vyšlo
2 272,0000000000005 a zaokrouhlení nahoru by dalo o korunu víc.
"""

from decimal import ROUND_CEILING, Decimal

SP_EMPLOYEE = Decimal('0.071')
SP_EMPLOYER = Decimal('0.248')
HEALTH_TOTAL = Decimal('0.135')


def _ceil(value):
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def insurance_contributions(assessment_base):
    """Vrací (SP zaměstnanec, ZP zaměstnanec, SP zaměstnavatel, ZP zaměstnavatel) v celých korunách."""
    base = Decimal(str(assessment_base or 0))
    if base <= 0:
        return 0, 0, 0, 0
    health_total = _ceil(base * HEALTH_TOTAL)
    health_employee = _ceil(Decimal(health_total) / 3)
    return (
        _ceil(base * SP_EMPLOYEE),
        health_employee,
        _ceil(base * SP_EMPLOYER),
        health_total - health_employee,
    )
