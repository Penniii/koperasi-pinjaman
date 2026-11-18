from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def rupiah(nilai):
    """1000000 -> Rp1.000.000 | 1816.67 -> Rp1.816,67 | -5000 -> -Rp5.000"""
    nilai = Decimal(str(nilai if nilai is not None else 0))
    negatif = nilai < 0
    teks = f"{abs(nilai):,.2f}"
    teks = teks.replace(",", "#").replace(".", ",").replace("#", ".")
    if teks.endswith(",00"):
        teks = teks[:-3]
    return ("-Rp" if negatif else "Rp") + teks