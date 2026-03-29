"""Vector Store - Ports & Adapters.

Este pacote implementa o padrão Hexagonal Architecture para o banco vetorial.
O código de negócio depende apenas da interface abstrata `VectorStorePort`;
os adapters concretos (Qdrant, Pinecone) são injetados via factory.
"""

from .port import VectorStorePort, SearchResult, VectorDocument
from .factory import create_vector_store

__all__ = [
    "VectorStorePort",
    "SearchResult",
    "VectorDocument",
    "create_vector_store",
]
