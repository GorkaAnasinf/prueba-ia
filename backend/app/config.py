from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI Platform API"
    api_key: str = "sk-change-me"
    litellm_base_url: str = "http://aiplatform-litellm:4000"
    litellm_master_key: str = "sk-change-me"
    database_url: str = "postgresql://aiplatform:password@aiplatform-postgres:5432/aiplatform"
    redis_url: str = "redis://:password@aiplatform-redis:6379"
    qdrant_url: str = "http://aiplatform-qdrant:6333"
    ollama_base_url: str = "http://aiplatform-ollama:11434"
    embed_model: str = "nomic-embed-text"
    rag_collection: str = "obsidian"
    obsidian_vault_path: str = "/obsidian-vault"

    class Config:
        env_file = ".env"


settings = Settings()
