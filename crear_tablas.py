from app.database import engine
from app.models import Base

Base.metadata.create_all(engine)
print("Tablas creadas OK en:", engine.url.host)