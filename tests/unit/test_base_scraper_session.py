
from unittest.mock import Mock, patch
import app.container # Register module
from app.scrapers.base_scraper import BaseScraper
import requests

class TestBaseScraperSession:

    @patch("app.container.get_container")
    def test_setup_initializes_session(self, mock_get_container):
        # Setup mock container
        mock_tracker = Mock()
        mock_get_container.return_value.state_tracker.return_value = mock_tracker

        # Create scraper
        class TestScraper(BaseScraper):
            name = "test"
            display_name = "Test"
            def scrape(self): pass
            def _init_driver(self): return Mock()

        scraper = TestScraper()

        # Run setup
        with patch.object(scraper, "_init_driver") as mock_init_driver:
             scraper.setup()

             # Verify session is initialized
             assert isinstance(scraper._session, requests.Session)
             assert scraper._session.headers["User-Agent"] == "TestScraper/1.0"

             # Verify driver initialization (since skip_webdriver is False by default)
             mock_init_driver.assert_called_once()

    @patch("app.container.get_container")
    def test_setup_initializes_session_skip_webdriver(self, mock_get_container):
        # Setup mock container
        mock_tracker = Mock()
        mock_get_container.return_value.state_tracker.return_value = mock_tracker

        # Create scraper
        class TestScraper(BaseScraper):
            name = "test"
            display_name = "Test"
            skip_webdriver = True
            def scrape(self): pass
            def _init_driver(self): return Mock()

        scraper = TestScraper()

        # Run setup
        with patch.object(scraper, "_init_driver") as mock_init_driver:
            scraper.setup()

            # Verify session is initialized
            assert isinstance(scraper._session, requests.Session)

            # Verify driver NOT initialized
            mock_init_driver.assert_not_called()

    @patch("app.container.get_container")
    def test_teardown_closes_session(self, mock_get_container):
         # Setup mock container
        mock_tracker = Mock()
        mock_get_container.return_value.state_tracker.return_value = mock_tracker

        # Create scraper
        class TestScraper(BaseScraper):
            name = "test"
            display_name = "Test"
            def scrape(self): pass

        scraper = TestScraper()
        scraper._session = Mock()
        mock_session = scraper._session
        scraper.driver = Mock()
        mock_driver = scraper.driver

        # Run teardown
        scraper.teardown()

        # Verify session closed and set to None
        mock_session.close.assert_called_once()
        assert scraper._session is None

        # Verify driver quit
        mock_driver.quit.assert_called_once()
