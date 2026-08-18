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
    # Behind TLS the session cookie must be Secure, or a single plain-HTTP
    # request leaks it. It cannot simply default to True: on a plain-HTTP
    # deployment a Secure cookie is never sent back, and sign-in appears to
    # succeed and then immediately fail — so it is a deliberate setting rather
    # than a guess about the environment.
    session_cookie_secure: bool = False

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
