"""
RetailFlow POS - Application Configuration
Uses pydantic-settings for environment-based configuration.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # Application
    app_name: str = "RetailFlow POS"
    app_version: str = "1.0.0"
    app_env: str = "development"
    app_debug: bool = True

    # Database
    database_type: str = "sqlite"
    database_url: str = "sqlite:///data/retailflow.db"

    # Security
    secret_key: str = "change-this-to-a-random-secret-string"
    argon2_memory_cost: int = 65536
    argon2_time_cost: int = 3
    argon2_parallelism: int = 4

    # Session & Authentication
    session_timeout_minutes: int = 30
    max_login_attempts: int = 5
    lockout_minutes: int = 15
    password_min_length: int = 8
    password_expiry_days: int = 90
    password_history_count: int = 5

    # Backup
    backup_directory: str = "backups"
    backup_retention_count: int = 30
    auto_backup_enabled: bool = True
    auto_backup_interval_hours: int = 24

    # Logging
    log_directory: str = "logs"
    log_level: str = "DEBUG"
    log_max_bytes: int = 10_485_760  # 10 MB
    log_backup_count: int = 10

    # File Paths
    export_directory: str = "exports"
    report_directory: str = "reports"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def base_dir(self) -> Path:
        """Absolute path to the project root directory."""
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def log_dir(self) -> Path:
        path = self.base_dir / self.log_directory
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def backup_dir(self) -> Path:
        path = self.base_dir / self.backup_directory
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def export_dir(self) -> Path:
        path = self.base_dir / self.export_directory
        path.mkdir(parents=True, exist_ok=True)
        return path


# Singleton settings instance
settings = Settings()