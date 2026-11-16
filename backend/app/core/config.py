from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:codecompass_dev_password@localhost:5433/codecompass"
    groq_api_key: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    session_secret: str = "change-this-before-production"
    auth_token_expire_minutes: int = 10080
    chat_requests_per_minute: int = 20
    daily_token_budget: int = 50000
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    github_redirect_uri: str = ""
    auth_cookie_secure: bool = False
    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_embedding_model: str = "@cf/baai/bge-small-en-v1.5"
    enable_reranker: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
