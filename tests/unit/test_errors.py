from app.utils.errors import ScraperError, NetworkError, ParsingError


def test_scraper_error_with_context():
    error = ScraperError("Test error", scraper="demo", context={"url": "http://example.com"})
    assert error.scraper == "demo"
    assert error.context["url"] == "http://example.com"
    assert error.recoverable is True
    assert "demo" in str(error)


def test_network_error_recoverable_by_default():
    error = NetworkError("Connection timeout", scraper="demo")
    assert error.recoverable is True


def test_parsing_error_not_recoverable_by_default():
    error = ParsingError("Parse failed", scraper="demo")
    assert error.recoverable is False
