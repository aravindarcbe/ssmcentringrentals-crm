from decimal import Decimal, InvalidOperation


def format_amount(value):
    """Format a money value without a pointless '.00' (34.00 -> '34', 34.20 -> '34.2')."""
    try:
        d = Decimal(value if value is not None else 0).quantize(Decimal("0.01"))
    except InvalidOperation:
        return str(value)
    text = f"{d:,.2f}"
    if text.endswith(".00"):
        return text[:-3]
    return text.rstrip("0") if "." in text else text
