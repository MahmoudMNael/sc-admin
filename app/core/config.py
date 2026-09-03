from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "CRUD API"
    ENV: str = "local"

    MONGO_URI: str
    MONGO_DB_NAME: str = "app"

    POSTGRES_DSN: str | None = None  # not used yet — make required once the first SQL module lands

    LOCAL_STORAGE_PATH: str = "./uploads"


settings = Settings()
