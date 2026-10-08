from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_db

app = FastAPI(title="SmartRiego API")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    productos = db.execute(text("SELECT COUNT(*) FROM productos")).scalar()
    return {"estado": "ok", "productos_en_base": productos}