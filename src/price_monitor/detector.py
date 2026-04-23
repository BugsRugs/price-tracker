from __future__ import annotations


def drop_pct(prev_price: float, new_price: float) -> float:
    """Return the percentage decrease from prev_price to new_price.

    Positive means a drop; negative means a rise.
    Caller must guard against prev_price <= 0.
    """
    return (prev_price - new_price) / prev_price * 100.0


def is_drop(prev_price: float, new_price: float, threshold_pct: float) -> bool:
    """Return True if the price dropped by at least threshold_pct percent.

    Returns False when prev_price <= 0 to guard against division by zero
    or meaningless comparisons against a zero/negative baseline.
    """
    if prev_price <= 0:
        return False
    return drop_pct(prev_price, new_price) >= threshold_pct
