"""
Měsíční záloha na daň ze závislé činnosti, slevy na dani a daňové zvýhodnění na děti
podle zákona č. 586/1992 Sb. ve znění pro zdaňovací období 2026.

- § 38h: základ zálohy do 100 Kč na celé koruny nahoru, nad 100 Kč na stokoruny nahoru;
  sazba 15 % do 3násobku průměrné mzdy, 23 % nad; záloha na celé koruny nahoru.
- § 35ba, § 35c, § 35d: slevy a zvýhodnění jen s podepsaným prohlášením (§ 38k odst. 4),
  měsíčně 1/12 roční částky; sleva nejvýš do výše zálohy, zbytek zvýhodnění na děti
  je daňový bonus (vyplácí se od 50 Kč a jen při příjmu aspoň poloviny minimální mzdy).
"""

import math
from dataclasses import dataclass, field

# Hodnoty pro rok 2026
AVERAGE_WAGE = 48_967                     # nařízení vlády č. 365/2025 Sb.
MINIMUM_WAGE = 22_400
HIGHER_RATE_LIMIT = 3 * AVERAGE_WAGE      # 146 901 Kč měsíčně
HALF_MINIMUM_WAGE = MINIMUM_WAGE // 2     # 11 200 Kč – podmínka pro daňový bonus
MIN_MONTHLY_BONUS = 50                    # § 35d odst. 4

# Měsíční slevy (1/12 ročních částek z § 35ba odst. 1)
MONTHLY_BASIC_CREDIT = 30_840 // 12       # 2 570 Kč
MONTHLY_DISABILITY_CREDIT = {'BASIC': 2_520 // 12, 'EXTENDED': 5_040 // 12}   # 210 / 420 Kč
MONTHLY_ZTPP_CREDIT = 16_140 // 12        # 1 345 Kč
# Daňové zvýhodnění na dítě (§ 35c odst. 1) – měsíčně; dítě se ZTP/P dvojnásobek
MONTHLY_CHILD_CREDIT = {'1': 15_204 / 12, '2': 22_320 / 12, '3': 27_840 / 12}  # 1 267 / 1 860 / 2 320 Kč


@dataclass
class MonthlyCredits:
    """Co si zaměstnanec za měsíc uplatňuje podle podepsaného prohlášení."""
    has_declaration: bool = False
    basic: int = 0
    disability: int = 0
    ztpp: int = 0
    children: int = 0
    children_detail: list = field(default_factory=list)

    @property
    def personal(self):
        return self.basic + self.disability + self.ztpp


def monthly_credits(employee, year, month):
    """Slevy a zvýhodnění za měsíc podle prohlášení, které v tom měsíci platí."""
    from core.models import TaxDeclaration

    declaration = TaxDeclaration.effective_for(employee, year, month)
    if declaration is None:
        return MonthlyCredits()
    credits = MonthlyCredits(
        has_declaration=True,
        basic=MONTHLY_BASIC_CREDIT if declaration.basic_credit else 0,
        disability=MONTHLY_DISABILITY_CREDIT.get(declaration.disability, 0),
        ztpp=MONTHLY_ZTPP_CREDIT if declaration.ztpp else 0,
    )
    for child in declaration.children.all():
        if child.claim not in MONTHLY_CHILD_CREDIT:
            continue
        amount = round(MONTHLY_CHILD_CREDIT[child.claim] * (2 if child.ztpp else 1))
        credits.children += amount
        credits.children_detail.append((f"{child.first_name} {child.last_name}", child.get_claim_display(), amount))
    return credits


def advance_tax(gross):
    """Záloha na daň před slevami (§ 38h odst. 1–3)."""
    if gross <= 0:
        return 0
    base = math.ceil(gross) if gross <= 100 else math.ceil(gross / 100) * 100
    tax = min(base, HIGHER_RATE_LIMIT) * 0.15 + max(0, base - HIGHER_RATE_LIMIT) * 0.23
    return math.ceil(round(tax, 6))


def withholding_tax(gross):
    """Srážková daň 15 % (§ 36 odst. 2) – základ i daň na celé koruny dolů."""
    return math.floor(math.floor(gross) * 0.15) if gross > 0 else 0


def apply_credits(tax_before_credits, gross, credits):
    """
    Uplatní slevy a zvýhodnění (§ 35d). Vrací (záloha po slevách, daňový bonus,
    uplatněná sleva na poplatníka a další osobní slevy, uplatněná sleva na děti).
    """
    personal_used = min(tax_before_credits, credits.personal)
    after_personal = tax_before_credits - personal_used
    child_used = min(after_personal, credits.children)
    tax = after_personal - child_used

    bonus = credits.children - child_used
    if bonus < MIN_MONTHLY_BONUS or gross < HALF_MINIMUM_WAGE:
        bonus = 0
    return tax, bonus, personal_used, child_used
