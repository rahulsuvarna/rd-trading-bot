STANDARD_SUFFIX = "_US_EQ"


def normalize_trading212_symbol(symbol: str) -> str:
    """Ensure symbol ends with Trading 212 US equity suffix."""
    s = str(symbol or "").strip().upper()
    if not s:
        return s
    if s.endswith(STANDARD_SUFFIX):
        return s
    return f"{s}{STANDARD_SUFFIX}"


def to_data_provider_symbol(ticker: str, provider: str = "yahoo") -> str:
    provider_name = str(provider or "yahoo").strip().lower()
    if provider_name in {"yahoo", "alpaca"}:
        return str(ticker or "").strip().upper().replace(STANDARD_SUFFIX, "")
    if provider_name == "trading212":
        return normalize_trading212_symbol(ticker)
    return str(ticker or "").strip().upper()


def to_display_symbol(ticker: str) -> str:
    return str(ticker or "").strip().upper().replace(STANDARD_SUFFIX, "")
