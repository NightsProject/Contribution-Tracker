import re

MAX_AMOUNT_CENTAVOS = 2_147_483_647
AMOUNT_PATTERN = re.compile(r"^[0-9]{1,9}(?:\.[0-9]{1,2})?$")


def parse_amount_centavos(value: str) -> int | None:
    amount = value.strip()
    if not AMOUNT_PATTERN.fullmatch(amount):
        return None
    whole, _, fractional = amount.partition(".")
    centavos = int(whole) * 100 + int(fractional.ljust(2, "0") or "0")
    if centavos <= 0 or centavos > MAX_AMOUNT_CENTAVOS:
        return None
    return centavos


def format_amount(amount_centavos: int) -> str:
    return f"{amount_centavos // 100:,}.{amount_centavos % 100:02d}"


def format_amount_input(amount_centavos: int) -> str:
    return f"{amount_centavos // 100}.{amount_centavos % 100:02d}"
