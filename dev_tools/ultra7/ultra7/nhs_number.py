"""UK NHS Number generation and Modulus 11 validation for synthetic test data."""
from __future__ import annotations

import random

# 999xxxxxxx is reserved for synthetic/test NHS numbers so generated values never
# collide with real patient records.
_DEFAULT_PREFIX = "999"


def compute_check_digit(first_nine: str) -> int | None:
    """Compute the NHS Number Mod-11 check digit for a 9-digit string.

    Returns ``None`` if the remainder is 10 (invalid number per NHS specification).
    """
    if len(first_nine) != 9 or not first_nine.isdigit():
        return None
    total = sum(int(digit) * weight for digit, weight in zip(first_nine, range(10, 1, -1)))
    remainder = 11 - (total % 11)
    if remainder == 11:
        return 0
    if remainder == 10:
        return None
    return remainder


def is_valid_nhs_number(value: str) -> bool:
    """Validate a 10-digit NHS Number (spaces/hyphens ignored) using Modulus 11."""
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) != 10:
        return False
    check = compute_check_digit(digits[:9])
    return check is not None and check == int(digits[9])


def generate_nhs_number(
    rng: random.Random | None = None,
    *,
    spaced: bool = False,
    prefix: str = _DEFAULT_PREFIX,
) -> str:
    """Generate a valid synthetic 10-digit UK NHS Number using Modulus 11.

    Uses a deterministic RNG if supplied (useful for reproducible previews/tests).
    """
    generator = rng if rng is not None else random.Random()  # nosec B311 - synthetic test data only
    clean_prefix = "".join(ch for ch in prefix if ch.isdigit())[:8] or _DEFAULT_PREFIX
    remaining = 9 - len(clean_prefix)

    while True:
        body = "".join(str(generator.randint(0, 9)) for _ in range(remaining))
        first_nine = clean_prefix + body
        check = compute_check_digit(first_nine)
        if check is not None:
            digits = f"{first_nine}{check}"
            if spaced:
                return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
            return digits
