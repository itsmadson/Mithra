from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mapillary_token: SecretStr
    database_url: str
    redis_url: str = "redis://localhost:6381/0"
    https_proxy: str | None = None
    crop_dir: str = "./data/crops"
    low_confidence_threshold: float = 0.45

    @field_validator("mapillary_token")
    @classmethod
    def _token_shape(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().startswith("MLY|"):
            raise ValueError("MAPILLARY_TOKEN must start with 'MLY|'")
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
