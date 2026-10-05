import re

def normalize_phone(raw: str, default_cc: str = '27') -> str:
    """Return E.164-ish form: +27728672014"""
    if not raw:
        return ''
    digits = re.sub(r'\D', '', raw)
    if digits.startswith('0'):
        digits = default_cc + digits[1:]
    elif not digits.startswith(default_cc):
        digits = default_cc + digits
    return f'+{digits}'