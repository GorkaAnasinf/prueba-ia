from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI Platform API"
    litellm_base_url: str = "http://litellm:4000"
    litellm_master_key: str = "sk-change-me"

    class Config:
        env_file = ".env"


settings = Settings()
