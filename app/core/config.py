from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized, environment-driven configuration.

    Credentials live here and nowhere else. Never log or print the
    password or either database URL.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    APP_ENV: str = "dev"

    # Trained artifacts, loaded once at startup. Training never happens in the
    # request path.
    MODEL_PATH: Path = Path("artifacts/xgboost_model.json")
    MODEL_METADATA_PATH: Path = Path("artifacts/model_metadata.json")
    # When true, a missing or malformed model artifact fails startup instead of
    # letting the service run without the thing it exists to serve. Set false
    # for tests and for working on the payment path before a model exists.
    REQUIRE_MODEL: bool = True

    @property
    def async_database_url(self) -> str:
        """URL for the application's async engine (asyncpg driver)."""
        return self._database_url("postgresql+asyncpg")

    @property
    def sync_database_url(self) -> str:
        """URL for synchronous consumers such as Alembic and the ML pipeline."""
        return self._database_url("postgresql+psycopg")

    def _database_url(self, driver: str) -> str:
        return (
            f"{driver}://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
