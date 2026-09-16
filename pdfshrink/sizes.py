"""Parse and display file sizes in French or English units."""

import re

KO = 1024
MO = 1024 * 1024

_UNITS = {"": KO, "KO": KO, "KB": KO, "K": KO, "MO": MO, "MB": MO, "M": MO}
_PATTERN = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([A-Z]*)$")


def parse_size(text):
    """Return bytes. A bare number means Ko. Raises ValueError on junk."""
    if not isinstance(text, str):
        raise ValueError("size must be text")
    cleaned = text.strip().upper().replace(" ", "").replace("\xa0", "")
    match = _PATTERN.match(cleaned)
    if not match:
        raise ValueError("cannot read size: %r" % text)
    number, unit = match.groups()
    if unit not in _UNITS:
        raise ValueError("unknown unit: %r" % unit)
    value = int(float(number.replace(",", ".")) * _UNITS[unit])
    if value <= 0:
        raise ValueError("size must be positive")
    return value


def _french_number(value):
    """1648 -> '1 648' with a narrow no-break space; 1.5 -> '1,5'."""
    if isinstance(value, float) and not value.is_integer():
        return ("%.1f" % value).replace(".", ",")
    return "{:,}".format(int(value)).replace(",", " ")


def format_size(n):
    """Always Ko, for showing document sizes: '1 648 Ko'."""
    return "%s Ko" % _french_number(round(n / KO))


def describe_size(n):
    """Largest sensible unit, for echoing what the user typed."""
    if n >= MO:
        return "%s Mo" % _french_number(round(n / MO, 1))
    return "%s Ko" % _french_number(round(n / KO))
