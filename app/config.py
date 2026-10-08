from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_user: str
    db_password: str
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "smartriego"

    secret_key: str
    algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24  # el token dura 24 horas

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()