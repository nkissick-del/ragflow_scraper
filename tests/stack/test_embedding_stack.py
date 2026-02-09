"""Stack tests for embedding client against real Ollama on Unraid."""

from app.services.embedding_client import OllamaEmbeddingClient


class TestOllamaEmbeddingStack:
    """Test embedding via Ollama on Unraid (192.168.1.101:11434)."""

    def test_connection(self, ollama_url, ollama_alive):
        client = OllamaEmbeddingClient(url=ollama_url, model="nomic-embed-text")
        assert client.test_connection() is True

    def test_embed_single(self, ollama_url, ollama_alive):
        client = OllamaEmbeddingClient(url=ollama_url, model="nomic-embed-text")
        vector = client.embed_single("Energy policy in Australia")
        assert len(vector) == 768
        assert all(isinstance(v, float) for v in vector)

    def test_embed_batch(self, ollama_url, ollama_alive):
        client = OllamaEmbeddingClient(url=ollama_url, model="nomic-embed-text")
        texts = [
            "Renewable energy targets for 2030",
            "Coal plant decommissioning schedule",
            "Solar farm construction permits",
        ]
        result = client.embed(texts)
        assert len(result.embeddings) == 3
        assert result.dimensions == 768
        assert result.model == "nomic-embed-text"

    def test_embed_empty_list(self, ollama_url, ollama_alive):
        client = OllamaEmbeddingClient(url=ollama_url, model="nomic-embed-text")
        result = client.embed([])
        assert result.embeddings == []
