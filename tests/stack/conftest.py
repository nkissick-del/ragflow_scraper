"""Stack test fixtures — require real services on Unraid."""

import os
import time

import pytest
import requests
from dotenv import load_dotenv


def pytest_configure(config):
    """Load .env.stack before test collection."""
    dotenv_path = os.getenv("DOTENV_PATH", ".env.stack")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path, override=True)
    # Ensure config module picks up the stack env vars
    os.environ.setdefault("NODE_ENV", "test")


# ---------------------------------------------------------------------------
# URL / credential fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def paperless_url():
    return os.environ.get("PAPERLESS_API_URL", "http://192.168.1.101:8000")


@pytest.fixture(scope="session")
def paperless_token():
    return os.environ.get("PAPERLESS_API_TOKEN", "")


@pytest.fixture(scope="session")
def anythingllm_url():
    return os.environ.get("ANYTHINGLLM_API_URL", "http://192.168.1.101:3151")


@pytest.fixture(scope="session")
def anythingllm_key():
    return os.environ.get("ANYTHINGLLM_API_KEY", "")


@pytest.fixture(scope="session")
def anythingllm_workspace():
    return os.environ.get("ANYTHINGLLM_WORKSPACE_ID", "test")


@pytest.fixture(scope="session")
def docling_serve_url():
    return os.environ.get("DOCLING_SERVE_URL", "http://192.168.1.101:4949")


# ---------------------------------------------------------------------------
# Health-check fixtures (skip gracefully if service unreachable)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def paperless_alive(paperless_url, paperless_token):
    """Skip if Paperless-ngx is not reachable."""
    try:
        resp = requests.get(
            f"{paperless_url}/api/",
            headers={"Authorization": f"Token {paperless_token}"},
            timeout=10,
        )
        if resp.ok:
            return True
    except Exception:
        pass
    pytest.skip("Paperless-ngx not reachable")


@pytest.fixture(scope="session")
def anythingllm_alive(anythingllm_url, anythingllm_key):
    """Skip if AnythingLLM is not reachable."""
    try:
        resp = requests.get(
            f"{anythingllm_url}/api/v1/workspaces",
            headers={"Authorization": f"Bearer {anythingllm_key}"},
            timeout=10,
        )
        if resp.ok:
            return True
    except Exception:
        pass
    pytest.skip("AnythingLLM not reachable")


@pytest.fixture(scope="session")
def docling_serve_alive(docling_serve_url):
    """Skip if docling-serve is not reachable."""
    try:
        resp = requests.get(f"{docling_serve_url}/health", timeout=10)
        if resp.ok:
            return True
    except Exception:
        pass
    pytest.skip("docling-serve not reachable")


@pytest.fixture(scope="session")
def gotenberg_url():
    return os.environ.get("GOTENBERG_URL", "http://192.168.1.101:3156")


@pytest.fixture(scope="session")
def gotenberg_alive(gotenberg_url):
    """Skip if Gotenberg is not reachable."""
    try:
        resp = requests.get(f"{gotenberg_url}/health", timeout=10)
        if resp.ok:
            return True
    except Exception:
        pass
    pytest.skip("Gotenberg not reachable")


@pytest.fixture(scope="session")
def pgvector_url():
    return os.environ.get("DATABASE_URL", "postgresql://scraper:scraper@192.168.1.101:5432/scraper_vectors")


@pytest.fixture(scope="session")
def pgvector_alive(pgvector_url):
    """Skip if PostgreSQL+pgvector is not reachable."""
    try:
        import psycopg
        with psycopg.connect(pgvector_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception:
        pass
    pytest.skip("PostgreSQL+pgvector not reachable")


@pytest.fixture(scope="session")
def ollama_url():
    return os.environ.get("EMBEDDING_URL", "http://192.168.1.101:11434")


@pytest.fixture(scope="session")
def ollama_alive(ollama_url):
    """Skip if Ollama is not reachable."""
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=10)
        if resp.ok:
            return True
    except Exception:
        pass
    pytest.skip("Ollama not reachable")


@pytest.fixture(scope="session")
def tika_url():
    return os.environ.get("TIKA_SERVER_URL", "http://192.168.1.101:9998")


@pytest.fixture(scope="session")
def tika_alive(tika_url):
    """Skip if Apache Tika is not reachable."""
    try:
        resp = requests.get(f"{tika_url}/tika", timeout=10)
        if resp.ok:
            return True
    except Exception:
        pass
    pytest.skip("Apache Tika not reachable")


# ---------------------------------------------------------------------------
# Test data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_pdf(tmp_path):
    """Create a minimal valid PDF with unique content per run.

    Embeds a timestamp in the PDF text to avoid Paperless-ngx duplicate detection.
    Computes xref byte offsets dynamically so the PDF is always structurally valid.
    """
    unique_id = str(int(time.time() * 1000))
    stream_content = f"BT /F1 12 Tf 100 700 Td (Stack test {unique_id}) Tj ET\n"
    stream_bytes = stream_content.encode("ascii")

    # Build each PDF object as bytes and record offsets
    buf = bytearray()
    offsets = {}

    buf.extend(b"%PDF-1.4\n")

    offsets[1] = len(buf)
    buf.extend(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    offsets[2] = len(buf)
    buf.extend(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

    offsets[3] = len(buf)
    buf.extend(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )

    offsets[4] = len(buf)
    buf.extend(f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii"))
    buf.extend(stream_bytes)
    buf.extend(b"endstream\nendobj\n")

    offsets[5] = len(buf)
    buf.extend(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    xref_offset = len(buf)
    buf.extend(b"xref\n0 6\n")
    buf.extend("0000000000 65535 f \n".encode("ascii"))
    for obj_num in range(1, 6):
        buf.extend(f"{offsets[obj_num]:010d} 00000 n \n".encode("ascii"))
    buf.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))

    pdf_path = tmp_path / f"test_document_{unique_id}.pdf"
    pdf_path.write_bytes(bytes(buf))
    return pdf_path


@pytest.fixture
def test_markdown(tmp_path):
    """Create a test markdown file."""
    md_path = tmp_path / "test_document.md"
    md_path.write_text(
        "# Test Document\n\nThis is a test document for stack testing.\n\n"
        "## Section 1\n\nSome content here.\n",
        encoding="utf-8",
    )
    return md_path


@pytest.fixture
def test_html(tmp_path):
    """Create a test HTML file."""
    html_path = tmp_path / "test_document.html"
    html_path.write_text(
        "<!DOCTYPE html>\n<html>\n<head><title>Test</title></head>\n"
        "<body><h1>Test Document</h1><p>Stack test content.</p></body>\n</html>",
        encoding="utf-8",
    )
    return html_path
