from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://legiswatch:legiswatch@localhost:5432/legiswatch"
    congress_api_key: str = ""
    govinfo_api_key: str = ""
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3:14b"
    llm_api_key: str = "ollama"
    fec_api_key: str = ""
    lda_api_key: str = ""
    lda_base_url: str = "https://lda.gov/api/v1"
    watch_poll_minutes: int = 0
    texas_ftp_host: str = "ftp.legis.state.tx.us"
    auto_discovery_enabled: bool = True
    auto_discovery_minutes: int = 10
    auto_discovery_batch_size: int = 50
    auto_discovery_us_congress: int = 119
    auto_discovery_tx_sessions: str = "89R"

settings = Settings()
