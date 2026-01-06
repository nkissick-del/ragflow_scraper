# Scraper Development Handoff Prompt

Use this prompt with Claude (in Chrome or another interface) to analyze a website and generate the information needed to build a new scraper.

---

## The Prompt

Copy and paste this when you're on the target website:

```
I need to build a web scraper for this page. Please analyze the page structure and provide the following information:

## 1. Page Overview
- What is the URL?
- What type of content does this page list?
  - **Downloadable files** (PDFs, Word docs, Excel) - we download and store the files
  - **HTML articles/news** - we extract content as Markdown and store it
  - **Mixed** - some of each
- Is the content rendered server-side or client-side (JavaScript)?
- Is there Cloudflare or other bot protection? (Look for "Just a moment..." or challenge pages)

## 2. Document List Structure
Identify the CSS selectors for:
- The container element that holds all document items
- Individual document items (the repeating element)
- For each document item, find selectors for:
  - Title
  - URL/link to the document
  - Publication date (and what format is the date in? Is the year included?)
  - File size (if shown)
  - File type indicator (if shown)
  - Category/tags (if shown)
  - Abstract/summary (if shown)

## 3. Pagination
- How does pagination work?
  - Traditional page links (?page=2)
  - Hash fragments (#page=2 or #offset=10)
  - Infinite scroll
  - Load more button
  - API-based
- What is the pagination URL pattern?
- How many items per page?
- How can we detect the total number of pages?
- Provide example URLs for pages 1, 2, and 3

## 4. Sample Data
Extract 2-3 sample documents with all their metadata as they appear on the page:
- Title
- URL
- Date
- Size
- Tags/category

## 5. Document Link Types
Analyze how documents are linked:
- Do listing page links go to **detail/landing pages** (HTML) that contain PDF download links?
- Or do listing page links go **directly to PDF files** (Content-Type: application/pdf)?
- Or is it a **mix of both**? (Some links are direct PDFs, others are landing pages)
- Or are these **HTML articles** where the content itself is on the detail page?

To check: Click a few document links and note:
- Does the browser show an HTML page with download buttons, or does it immediately download/display a PDF?
- What is the URL pattern? (e.g., `/assets/uploads/*.pdf` vs `/resources/reports/document-name/`)

This is critical because:
- Direct PDF links: The scraper can download immediately from the listing URL
- Landing pages: The scraper must visit each page and find PDF links within
- HTML articles: The scraper must visit each page and extract content as Markdown
- Mixed: The scraper needs to check Content-Type headers before parsing

## 5a. Structured Data (JSON-LD)
Check if the site uses Schema.org structured data (common on news/article sites):
- Open browser DevTools → Elements → search for `application/ld+json`
- Or view page source and search for `"@type": "Article"` or similar

If JSON-LD exists, note:
- What `@type` is used? (Article, NewsArticle, WebPage, etc.)
- Does it contain `datePublished`, `dateModified`? (These are ISO 8601 format with year!)
- Does it contain `author`, `headline`, `description`?
- Is the JSON-LD on the listing page or only on individual article pages?

This is valuable because:
- JSON-LD dates include the full year (listing pages often show "Dec 24" without year)
- Structured data is more stable than CSS selectors during site redesigns
- It follows a standard schema, making parsing reliable

## 5b. Article Content Extraction (if HTML articles)
If the content is HTML articles (not downloadable files):
- What is the CSS selector for the main article body/content?
- Are there elements to exclude? (ads, related articles, navigation, share buttons)
- Does the article have images that should be preserved?
- What heading structure is used? (h1, h2, h3 for sections)

## 5c. RSS/Atom Feed (Check This First!)
Many sites provide RSS or Atom feeds that are much more efficient to scrape than HTML pages.

Check for feeds:
- Look for RSS/Atom icons on the page
- Check `<link rel="alternate" type="application/rss+xml">` in page source
- Try common feed URLs: `/feed`, `/rss`, `/atom`, `/feed.xml`, `/articles.atom`
- Check `/robots.txt` for feed URLs

If a feed exists, note:
- What is the feed URL?
- Does the feed include **full article content** in `<content>` tags? (This is the jackpot!)
- Or does it only include summaries/excerpts?
- What metadata is available? (title, author, dates, categories)
- Does the feed support pagination? (e.g., `?page=2`)
- How many items per feed page?

This is critical because:
- Feeds with full content = Single-stage scraping (no individual page visits needed)
- Feeds with summaries only = Still need two-stage scraping
- Feed-based scraping is ~25x more efficient than HTML scraping
- No Selenium required, just HTTP requests

## 6. Special Considerations
- Are there any documents that should be filtered out? (e.g., by category, file type)
- Are there any anti-bot measures beyond Cloudflare?
- Does the site require cookies or authentication?
- Are there any rate limiting concerns?

## 7. Recommended Approach
Based on your analysis, recommend:
- Should we use an RSS/Atom feed? (Always prefer this if full content is available!)
- Should we use FlareSolverr (Cloudflare bypass)?
- Should we parse the HTML directly or is there an API?
- Any special handling needed for this site?

Please provide the CSS selectors in a format I can copy directly into Python code.
```

---

## What You'll Receive

Claude should provide analysis like the examples below.

### Example 1: PDF Documents (AEMO)

```
## 1. Page Overview
- URL: https://www.aemo.com.au/library/major-publications
- Content: **Downloadable files** (PDF documents - energy reports, planning documents)
- Rendering: Client-side JavaScript (Sitecore SXA)
- Protection: Cloudflare (requires FlareSolverr)

## 2. Document List Structure
- Container: `ul.search-result-list`
- Items: `.search-result-list > li` or `a.search-result-list-item`
- Title: `h3` inside the link
- URL: `href` attribute of the `<a>` tag
- Date: `.is-date.field-publisheddate span` (format: DD/MM/YYYY - year included)
- Size: Look for "Size X.XX MB" in `.search-result-list-item--content`
- Type: `.field-extension` contains "pdf", "xlsx", etc.
- Category: First `<span>` in the link (e.g., "Document")

## 3. Pagination
- Type: Hash fragment offset
- Pattern: `#e={offset}` where offset = (page - 1) * 10
- Items per page: 10
- Examples:
  - Page 1: https://www.aemo.com.au/library/major-publications (or #e=0)
  - Page 2: https://www.aemo.com.au/library/major-publications#e=10
  - Page 3: https://www.aemo.com.au/library/major-publications#e=20
- Total pages: JS-rendered, default to ~22 pages

## 4. Sample Data
1. Title: "2025 WA Gas Statement of Opportunities"
   URL: /-/media/files/gas/.../2025-wa-gas-statement-of-opportunities.pdf
   Date: 19/12/2025
   Size: 2.29 MB
   Tags: Document

## 5. Document Link Types
- Type: Direct PDF links
- All listing links point directly to PDF files
- URL pattern: `/-/media/files/.../document.pdf`
- No landing pages to parse

## 5a. Structured Data
- No JSON-LD found

## 6. Special Considerations
- Filter out: Gas, Annual Report, Budget, Corporate publications
- Cloudflare protection active
- No authentication required

## 7. Recommended Approach
- Use FlareSolverr for Cloudflare bypass
- Parse HTML directly (no usable API)
- Use base class `init_cloudflare_and_fetch_first_page()` and `fetch_page()`
```

### Example 2: HTML Articles (TheEnergy)

```
## 1. Page Overview
- URL: https://theenergy.co/articles
- Content: **HTML articles** (news, features, explainers about energy industry)
- Rendering: Server-side (no JavaScript required)
- Protection: None (no Cloudflare)

## 2. Document List Structure
- Container: `main`
- Items: `article`
- Title: `article h3`
- URL: `article > a[href]`
- Date: `article .metadata .date` (format: "Dec 24 7:30am" - NO YEAR on listing page!)
- Category: `article .metadata span:first-child` (e.g., "Policy", "Projects")
- Type: `article .metadata span:nth-child(2)` (e.g., "news", "feature")
- Abstract: `article .abstract`

## 3. Pagination
- Type: Path-based
- Pattern: `/articles/pN` where N is page number
- Items per page: 10
- Examples:
  - Page 1: https://theenergy.co/articles
  - Page 2: https://theenergy.co/articles/p2
  - Page 3: https://theenergy.co/articles/p3
- Total pages: 34 (can detect from "Page X of Y" text)

## 4. Sample Data
1. Title: "10 charts that tell the story of energy in 2025"
   URL: https://theenergy.co/article/10-charts-that-tell-the-story-of-energy-in-2025
   Date: Dec 24 7:30am (listing) / 2025-12-24T07:30:00+11:00 (JSON-LD)
   Category: Policy
   Type: feature
   Abstract: "...and foreshadow what's to come in 2026"

## 5. Document Link Types
- Type: **HTML articles** (not PDFs)
- Listing links go to article pages with full content
- Must visit each article page to extract content and full dates

## 5a. Structured Data (JSON-LD)
- Found on individual article pages (NOT listing page)
- Type: `"@type": "Article"`
- Contains:
  - `datePublished`: "2025-12-24T07:30:00+11:00" (full ISO 8601 with year!)
  - `dateCreated`: "2025-12-24T12:04:37+11:00"
  - `dateModified`: "2025-12-24T12:39:08+11:00"
  - `headline`: Article title
- **Critical**: Listing page dates lack year - must fetch JSON-LD from article pages

## 5b. Article Content Extraction
- Content container: `article .content` or `article`
- Exclude: `nav, .navigation, .sidebar, .related, .share, .advertisement`
- Images: Yes, preserve as Markdown image links
- Headings: h1 for title, h2/h3 for sections

## 6. Special Considerations
- No authentication required
- No rate limiting observed
- Categories: Policy, Projects, Regulation, Energy Systems, Technology, Capital, Climate, Workforce
- Article types: news, feature, explainer, context

## 7. Recommended Approach
- No FlareSolverr needed (no Cloudflare)
- Two-stage scraping: listing page → article pages
- Extract JSON-LD for accurate dates with year
- Convert article HTML to Markdown using html2text
- Save as .md files with YAML frontmatter
```

### Example 3: Atom Feed with Full Content (The Conversation)

```text
## 1. Page Overview
- URL: https://theconversation.com/topics/energy-662
- Content: **HTML articles** (academic journalism about energy)
- Rendering: Server-side (no JavaScript required)
- Protection: None (no Cloudflare)

## 2. Document List Structure
- Container: `body`
- Items: `article`
- Title: `h2 a` or `h1 a`
- URL: `a[href^="/"]`
- Date: `time[datetime]` (ISO 8601 format with year!)
- Author: `a[href*="/profiles/"]`
- Summary: Last `<p>` in article

## 3. Pagination
- Type: Query parameter
- Pattern: `?page={N}`
- Items per page: 20
- Examples:
  - Page 1: https://theconversation.com/topics/energy-662
  - Page 2: https://theconversation.com/topics/energy-662?page=2
  - Page 3: https://theconversation.com/topics/energy-662?page=3
- Total pages: ~49 (965 articles)

## 5c. RSS/Atom Feed - THE KEY FINDING!
- **Feed URL**: https://theconversation.com/topics/energy-662/articles.atom
- **Full content included**: YES! `<content type="html">` contains ~10-17KB of full article HTML
- **Pagination**: `?page=2`, `?page=3`, etc.
- **Items per page**: 25

Feed entry structure:
```xml
<entry>
  <id>theconversation.com,2011:article/270866</id>
  <published>2026-01-02T11:39:36Z</published>
  <updated>2026-01-02T11:39:36Z</updated>
  <title>China's five green economy challenges in 2026</title>
  <link href="https://theconversation.com/chinas-..."/>
  <author><name>Chee Meng Tan</name></author>
  <summary>Brief excerpt...</summary>
  <content type="html"><!-- FULL ARTICLE HTML HERE --></content>
</entry>
```

## 6. Special Considerations

- No authentication required
- No rate limiting observed
- Creative Commons license (CC BY-ND)

## 7. Recommended Approach

- **USE THE ATOM FEED** - Contains full article content!
- No Selenium required (HTTP requests only)
- Single-stage scraping: parse feed entries directly
- ~39 HTTP requests vs ~1000+ for HTML scraping
- Use `feedparser` library for parsing
- Convert HTML content to Markdown using GFMConverter
- Save as .md files with YAML frontmatter
```

---

## Using the Information to Build a Scraper

Once you have the analysis, create a new scraper file in `/app/scrapers/`:

```python
"""
{Site Name} scraper for {content type}.

Scrapes {documents} from: {URL}

Uses FlareSolverr for Cloudflare bypass (if needed).
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.scrapers.base_scraper import BaseScraper, DocumentMetadata, ScraperResult
from app.utils import sanitize_filename, parse_file_size


class {SiteName}Scraper(BaseScraper):
    """
    Scraper for {Site Name}.

    Key features from analysis:
    - {pagination type}
    - {any special handling}
    """

    name = "{site_name}"  # lowercase, used for config and file paths
    description = "Scrapes {content} from {Site Name}"
    base_url = "{base_url}"

    # Pagination settings
    documents_per_page = {n}
    request_delay = 2.0

    # Tags to exclude (if any)
    excluded_tags = [
        # From analysis section 5
    ]

    def scrape(self) -> ScraperResult:
        """Main scraping logic."""
        result = ScraperResult(
            status="in_progress",
            scraper=self.name,
        )

        # Use base class method for Cloudflare bypass + first page fetch
        success, page_html = self.init_cloudflare_and_fetch_first_page()
        if not success:
            result.status = "failed"
            result.errors.append("Cloudflare challenge blocked access")
            return result

        # Detect pagination (site-specific logic)
        total_pages = self._detect_total_pages(page_html)
        pages_to_scrape = min(self.max_pages, total_pages) if self.max_pages else total_pages

        # Iterate through pages
        for page_num in range(pages_to_scrape):
            if self.check_cancelled():
                break

            # First page already fetched
            if page_num > 0:
                page_url = self._get_page_url(page_num)
                page_html = self.fetch_page(page_url)

            # Parse and process documents
            documents = self.parse_page(page_html)
            result.scraped_count += len(documents)

            for doc in documents:
                if self.check_cancelled():
                    break
                if self._should_exclude(doc.tags):
                    result.skipped_count += 1
                    continue
                if self._is_processed(doc.url):
                    result.skipped_count += 1
                    continue

                if self.dry_run:
                    self.logger.info(f"[DRY RUN] Would download: {doc.title}")
                    result.downloaded_count += 1
                    result.documents.append(doc.to_dict())
                else:
                    if self._download_file(doc.url, doc.filename, doc):
                        result.downloaded_count += 1
                        result.documents.append(doc.to_dict())
                        self._mark_processed(doc.url, {"title": doc.title})
                    else:
                        result.failed_count += 1

                self._polite_delay()

            self._polite_delay()

        return result

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        """Parse page HTML and extract document metadata."""
        soup = BeautifulSoup(page_source, "lxml")
        documents = []

        # Use selectors from analysis section 2
        items = soup.select("{item_selector}")

        for item in items:
            doc = self._parse_item(item)
            if doc:
                documents.append(doc)

        return documents

    def _parse_item(self, item) -> Optional[DocumentMetadata]:
        """Parse a single document item."""
        # Extract using selectors from analysis
        # ... implementation based on site structure
        pass

    def _get_page_url(self, page_num: int) -> str:
        """Build URL for a specific page."""
        # Use pattern from analysis section 3
        pass

    def _detect_total_pages(self, html: str) -> int:
        """Detect total pages from HTML."""
        # Use approach from analysis section 3
        pass

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date to ISO format."""
        # Use format from analysis section 2
        pass
```

---

## Base Class Methods Available

Your scraper inherits these from `BaseScraper`:

### Cloudflare Bypass
| Method | Description |
|--------|-------------|
| `init_cloudflare_and_fetch_first_page()` | Init bypass + fetch first page. Returns `(success, html)` |
| `fetch_page(url, use_cached=False)` | Fetch any page (auto FlareSolverr → Selenium fallback) |
| `fetch_page_via_flaresolverr(url)` | Low-level: FlareSolverr only |
| `has_cloudflare_session` | Property: True if bypass succeeded |

### Document Processing
| Method | Description |
|--------|-------------|
| `_is_processed(url)` | Check if URL already scraped |
| `_mark_processed(url, metadata)` | Mark URL as scraped |
| `_should_exclude(tags)` | Check if tags match `excluded_tags` |
| `_download_file(url, filename, metadata)` | Download with retries |
| `_polite_delay()` | Wait `request_delay` seconds |

### Utilities
| Method | Description |
|--------|-------------|
| `check_cancelled()` | Check if user cancelled |
| `self.logger` | Logger instance for this scraper |
| `self.dry_run` | True if preview/dry run mode |
| `self.max_pages` | Max pages to scrape (or None) |

---

## Checklist Before Testing

### All Scrapers

- [ ] Scraper file named `{name}_scraper.py` in `/app/scrapers/`
- [ ] Class inherits from `BaseScraper`
- [ ] `name` attribute is lowercase, unique
- [ ] `base_url` is set correctly
- [ ] `parse_page()` returns `list[DocumentMetadata]`
- [ ] `scrape()` returns `ScraperResult`
- [ ] Date parsing handles the site's format
- [ ] URL building handles relative URLs correctly
- [ ] Excluded tags configured (if needed)

### Additional for Article Scrapers

- [ ] JSON-LD extraction for full dates (if listing page lacks year)
- [ ] Article content extraction configured (html2text)
- [ ] Unwanted elements excluded (ads, nav, related articles)
- [ ] Images preserved as Markdown links (if desired)
- [ ] YAML frontmatter included in saved .md files

## Testing

- Enable FlareSolverr toggle in Settings (if needed)
- Enable per-scraper FlareSolverr toggle on Scrapers page
- Run Preview (Dry Run) with 1-2 pages
- Check logs for errors
- Verify document count and metadata look correct
- For article scrapers: verify .md files have correct frontmatter and clean content
