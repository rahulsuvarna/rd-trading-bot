from data.price_fetcher import to_yahoo_symbol


def test_trading212_aapl_converts_to_yahoo():
    assert to_yahoo_symbol("AAPL_US_EQ") == "AAPL"


def test_trading212_spy_converts_to_yahoo():
    assert to_yahoo_symbol("SPY_US_EQ") == "SPY"


def test_ticker_without_suffix_unchanged():
    assert to_yahoo_symbol("MSFT") == "MSFT"
