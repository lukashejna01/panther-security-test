"""
Šablonový filtr pro částky: {{ invoice.total_amount|kc }} → 12 345,50
Je zaregistrovaný jako builtin v settings (TEMPLATES), {% load %} není potřeba.
"""

from django import template

from core.money import format_amount

register = template.Library()


@register.filter
def kc(value, decimals=2):
    """Částka s mezerami mezi tisíci a desetinnou čárkou (např. 1 234,50)."""
    return format_amount(value, int(decimals))
