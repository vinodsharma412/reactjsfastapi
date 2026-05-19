"""Application configuration loaded from environment variables / .env file.

``Settings`` is a Pydantic ``BaseSettings`` class. On import it reads values
from the process environment and — if present — from a ``.env`` file in the
working directory. Type coercion and validation are handled automatically.

Example ``.env``::

    SECRET_KEY=change-me-in-production
    DB_HOST=localhost
    DB_NAME=myapp
    DB_USER=postgres
    DB_PASSWORD=secret
"""

from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Validated application settings read from environment / ``.env``."""

    APP_NAME: str = "MyApp"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # --- Authentication ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # --- Database ---
    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    # --- Gmail IMAP (optional — feature disabled if not set) ---
    GMAIL_USER: str = ""
    GMAIL_APP_PASSWORD: str = ""

    # --- Ollama local LLM (optional — analysis skipped if not set) ---
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"

    @property
    def DATABASE_URL(self) -> str:
        """Construct a SQLAlchemy-compatible PostgreSQL connection URL.

        ``quote_plus`` percent-encodes special characters (``@``, ``#``, ``%``)
        that may appear in the password, which would otherwise break URL parsing.

        Returns:
            A ``postgresql://user:password@host:port/dbname`` URL string.
        """
        password = quote_plus(self.DB_PASSWORD)
        return (
            f"postgresql://{self.DB_USER}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
