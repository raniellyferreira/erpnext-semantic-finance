"""Factory para instanciar o VectorStore correto baseado na configuração.

Princípio OCP (Open/Closed): para adicionar um novo provider basta
criar um novo adapter e registrá-lo no dicionário PROVIDERS.
"""

from ..config import settings
from .port import VectorStorePort


def create_vector_store() -> VectorStorePort:
    """Instancia o adapter de vector store configurado via VECTOR_STORE_PROVIDER.

    Returns:
        Instância do adapter que implementa VectorStorePort.

    Raises:
        ValueError: Se o provider configurado não for suportado.
    """
    provider = settings.vector_store_provider.lower()

    if provider == "qdrant":
        from .adapters.qdrant_adapter import QdrantAdapter
        return QdrantAdapter(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )

    if provider == "pinecone":
        from .adapters.pinecone_adapter import PineconeAdapter
        return PineconeAdapter(
            api_key=settings.pinecone_api_key,
            index_name=settings.pinecone_index_name,
            namespace=settings.pinecone_namespace,
            environment=settings.pinecone_environment or None,
        )

    raise ValueError(
        f"Vector store provider '{provider}' não suportado. "
        f"Opções disponíveis: qdrant, pinecone"
    )
