from pathlib import Path

from app.scrapers.models import DocumentMetadata
from app.services.ragflow_client import RAGFlowClient, UploadResult


def test_upload_documents_with_metadata_handles_duplicates_and_metadata_failure(monkeypatch, tmp_path):
    client = RAGFlowClient(api_url="http://example.com", api_key="dummy")

    file_one = tmp_path / "one.pdf"
    file_two = tmp_path / "two.pdf"
    file_one.write_text("doc-one")
    file_two.write_text("doc-two")

    doc_one = DocumentMetadata(url="https://example.com/1", title="Doc 1", filename="one.pdf", hash="dup-1")
    doc_two = DocumentMetadata(url="https://example.com/2", title="Doc 2", filename="two.pdf", hash="hash-2")

    upload_calls: list[str] = []
    metadata_calls: list[tuple[str, dict]] = []

    def fake_check(dataset_id: str, file_hash: str):
        return "existing-dup" if file_hash == "dup-1" else None

    def fake_upload(dataset_id: str, filepath: Path):
        upload_calls.append(filepath.name)
        return UploadResult(success=True, document_id=f"doc-{filepath.stem}", filename=filepath.name)

    def fake_wait(dataset_id: str, doc_id: str, timeout: float = 10.0, poll_interval: float = 0.5):
        return True

    def fake_set_metadata(dataset_id: str, doc_id: str, metadata: dict):
        metadata_calls.append((doc_id, metadata))
        return False  # simulate metadata push failure

    monkeypatch.setattr(client, "check_document_exists", fake_check)
    monkeypatch.setattr(client, "upload_document", fake_upload)
    monkeypatch.setattr(client, "wait_for_document_ready", fake_wait)
    monkeypatch.setattr(client, "set_document_metadata", fake_set_metadata)

    results = client.upload_documents_with_metadata(
        dataset_id="ds-1",
        docs=[{"filepath": file_one, "metadata": doc_one}, {"filepath": file_two, "metadata": doc_two}],
        check_duplicates=True,
    )

    assert len(results) == 2

    # First file skipped as duplicate
    assert results[0].success is True
    assert results[0].skipped_duplicate is True
    assert results[0].document_id == "existing-dup"
    assert upload_calls == ["two.pdf"]  # only non-duplicate uploaded

    # Second file uploaded but metadata push failed
    assert results[1].success is True
    assert results[1].metadata_pushed is False
    assert results[1].filename == "two.pdf"
    assert metadata_calls and metadata_calls[0][0] == "doc-two"


def test_upload_documents_with_metadata_propagates_upload_failure(monkeypatch, tmp_path):
    client = RAGFlowClient(api_url="http://example.com", api_key="dummy")

    file_path = tmp_path / "fail.pdf"
    file_path.write_text("fail")
    doc = DocumentMetadata(url="https://example.com/fail", title="Fail", filename="fail.pdf", hash="h1")

    def fake_upload(dataset_id: str, filepath: Path):
        return UploadResult(success=False, error="boom", filename=filepath.name)

    monkeypatch.setattr(client, "upload_document", fake_upload)

    results = client.upload_documents_with_metadata(
        dataset_id="ds-err",
        docs=[{"filepath": file_path, "metadata": doc}],
        check_duplicates=False,
    )

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error == "boom"
    assert results[0].metadata_pushed is False
