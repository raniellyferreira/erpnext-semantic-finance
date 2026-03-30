"""Vector Store - Ports & Adapters.

Este pacote implementa o padrão Hexagonal Architecture para o banco vetorial.
O código de negócio depende apenas da interface abstrata `VectorStorePort`;
os adapters concretos (Qdrant, Pinecone) são injetados via factory.

O ``EmbeddingService`` converte texto em vetores usando o provedor configurado
(Ollama, OpenAI ou Voyage AI).
"""

from .embeddings import EmbeddingService
from .factory import create_vector_store
from .port import SearchFilter, SearchResult, VectorDocument, VectorStorePort

__all__ = [
    "VectorStorePort",
    "SearchResult",
    "SearchFilter",
    "VectorDocument",
    "create_vector_store",
    "EmbeddingService",
]
