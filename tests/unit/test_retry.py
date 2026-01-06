import pytest

from app.utils.errors import NetworkError, ParsingError
from app.utils.retry import retry_on_error


def test_retry_succeeds_on_second_attempt():
    calls = []

    @retry_on_error(max_attempts=3, backoff_factor=0.01, exceptions=(NetworkError,))
    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise NetworkError("temporary failure", scraper="demo")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 2


def test_retry_gives_up_after_max_attempts():
    @retry_on_error(max_attempts=2, backoff_factor=0.01, exceptions=(NetworkError,))
    def always_fails():
        raise NetworkError("still failing", scraper="demo")

    with pytest.raises(NetworkError):
        always_fails()


def test_non_recoverable_not_retried():
    attempts = []

    @retry_on_error(max_attempts=3, backoff_factor=0.01, exceptions=(ParsingError,))
    def not_recoverable():
        attempts.append(1)
        raise ParsingError("parse error", scraper="demo", recoverable=False)

    with pytest.raises(ParsingError):
        not_recoverable()

    assert len(attempts) == 1
