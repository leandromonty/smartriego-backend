from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from .config import settings

url = URL.create(
    "mysql+pymysql",
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
)

# Aiven exige SSL. En local (127.0.0.1 / localhost) no hace falta.
_es_local = settings.db_host in ("127.0.0.1", "localhost")
_connect_args = {} if _es_local else {"ssl": {"check_hostname": False}}

engine = create_engine(url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()