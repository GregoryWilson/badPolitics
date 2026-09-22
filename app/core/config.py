from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://legiswatch:legiswatch@localhost:5432/legiswatch"
    congress_api_key: str = ""
    govinfo_api_key: str = ""
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3:14b"
    llm_api_key: str = "ollama"

settings = Settings()
