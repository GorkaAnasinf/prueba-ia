from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI Platform API"
    api_key: str = "sk-change-me"
    litellm_base_url: str = "http://aiplatform-litellm:4000"
    litellm_master_key: str = "sk-change-me"
    database_url: str = "postgresql://aiplatform:password@aiplatform-postgres:5432/aiplatform"
    redis_url: str = "redis://:password@aiplatform-redis:6379"

    class Config:
        env_file = ".env"


settings = Settings()
