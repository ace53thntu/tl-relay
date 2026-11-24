from pricing.settings import PRICING_TIMEOUT_SECONDS


def submit_order(order: dict) -> dict:
    return {**order, "timeout": PRICING_TIMEOUT_SECONDS}
