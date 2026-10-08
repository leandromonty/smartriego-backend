from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_user: str
    db_password: str
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "smartriego"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()