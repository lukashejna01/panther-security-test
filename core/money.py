"""
Jednotný český formát částek: 1 234 567,50 (mezery mezi tisíci, desetinná čárka).
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Nezalomitelná mezera – částka se v tabulce nerozdělí na dva řádky
THOUSANDS_SEPARATOR = '\xa0'


def format_amount(value, decimals=2, separator=THOUSANDS_SEPARATOR):
    """Číslo/Decimal/float na „12 345,50“. Hodnoty, které nejsou číslo, vrací beze změny."""
    if value is None or value == '':
        return ''
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    if not number.is_finite():
        return value
    number = number.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    text = f"{abs(number):,.{decimals}f}".replace(',', separator).replace('.', ',')
    return f"-{text}" if number < 0 else text
