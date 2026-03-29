"""Configurações do MCP Server via variáveis de ambiente."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações carregadas do .env ou variáveis de ambiente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ERPNext
    erpnext_url: str = "http://localhost:8080"
    erpnext_api_key: str = ""
    erpnext_api_secret: str = ""
    erpnext_site_name: str = "mysite.localhost"
    erpnext_default_company: str = ""

    # ─── Vector Store ──────────────────────────────────────────────────────────
    # Opções: qdrant | pinecone
    vector_store_provider: str = "qdrant"

    # Qdrant (self-hosted ou Qdrant Cloud)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_environment: str = ""          # ex: us-east-1-aws (legado) ou leave empty for serverless
    pinecone_index_name: str = "erpnext-finance"
    pinecone_namespace: str = "default"     # namespace para multi-tenancy

    # ─── Embeddings ────────────────────────────────────────────────────────────
    # Opções: ollama | openai
    embedding_provider: str = "ollama"
    embedding_dimension: int = 768          # 768 para nomic-embed-text, 1536 para text-embedding-3-small

    # Ollama (recomendado para dados sensíveis - 100% local)
    ollama_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"

    # OpenAI (melhor qualidade, dados enviados para API externa - atenção à LGPD)
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    # Voyage AI (modelos open-source de alta qualidade para embeddings)
    voyage_api_key: str = ""
    voyage_embedding_model: str = "voyage-3-large"
    voyage_api_url: str = "https://api.voyageai.com"

    # ─── Focus NF-e ────────────────────────────────────────────────────────────
    focus_nfe_token: str = ""
    focus_nfe_environment: str = "homologacao"  # homologacao | producao
    focus_nfe_url_homologacao: str = "https://homologacao.focusnfe.com.br"
    focus_nfe_url_producao: str = "https://api.focusnfe.com.br"

    # ─── MCP Server ────────────────────────────────────────────────────────────
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8000
    log_level: str = "INFO"

    @property
    def focus_nfe_url(self) -> str:
        """Retorna a URL correta baseada no ambiente configurado."""
        if self.focus_nfe_environment == "producao":
            return self.focus_nfe_url_producao
        return self.focus_nfe_url_homologacao

    @property
    def erpnext_auth_header(self) -> str:
        """Retorna o header de autenticação para a API ERPNext."""
        return f"token {self.erpnext_api_key}:{self.erpnext_api_secret}"


settings = Settings()
