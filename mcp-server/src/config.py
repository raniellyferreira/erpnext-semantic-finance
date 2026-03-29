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

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # Embeddings
    embedding_provider: str = "ollama"  # ollama | openai
    ollama_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    # Focus NF-e
    focus_nfe_token: str = ""
    focus_nfe_environment: str = "homologacao"  # homologacao | producao
    focus_nfe_url_homologacao: str = "https://homologacao.focusnfe.com.br"
    focus_nfe_url_producao: str = "https://api.focusnfe.com.br"

    # MCP Server
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
