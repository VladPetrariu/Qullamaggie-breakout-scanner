from scanner.universe import _is_fund_name


def test_fund_keywords_catch_real_funds():
    """Names carrying a fund/ETF word are caught."""
    assert _is_fund_name("SPDR S&P 500 ETF TRUST")
    assert _is_fund_name("INVESCO DB AGRICULTURE FUND")
    assert _is_fund_name("ProShares Trust II")
    assert _is_fund_name("Hashdex Nasdaq CME Crypto Index ETF")
    assert _is_fund_name("21Shares Dogecoin ETF")


def test_real_companies_are_not_caught():
    """Names that use a fund-adjacent word for an unrelated reason pass through."""
    assert not _is_fund_name("NORTHERN TRUST CORP")
    assert not _is_fund_name("ALTISOURCE PORTFOLIO SOLUTIONS S.A.")
    assert not _is_fund_name("CONSUMER PORTFOLIO SERVICES, INC.")
    assert not _is_fund_name("NUVEEN SELECT TAX FREE INCOME PORTFOLIO")