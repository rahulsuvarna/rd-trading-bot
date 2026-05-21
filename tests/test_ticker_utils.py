from utils.ticker_utils import to_data_provider_symbol, to_display_symbol


def test_to_data_provider_yahoo():
    assert to_data_provider_symbol("AAPL_US_EQ", "yahoo") == "AAPL"


def test_to_data_provider_alpaca():
    assert to_data_provider_symbol("AAPL_US_EQ", "alpaca") == "AAPL"


def test_to_data_provider_trading212_keeps_suffix():
    assert to_data_provider_symbol("AAPL_US_EQ", "trading212") == "AAPL_US_EQ"


def test_to_data_provider_trading212_adds_suffix():
    assert to_data_provider_symbol("AAPL", "trading212") == "AAPL_US_EQ"


def test_to_display_symbol_removes_suffix():
    assert to_display_symbol("AAPL_US_EQ") == "AAPL"


def test_to_display_symbol_keeps_plain_ticker():
    assert to_display_symbol("AAPL") == "AAPL"
