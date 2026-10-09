from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_db
from .routers import auth, dispositivos, equipo, pedidos, productos

app = FastAPI(title="SmartRiego API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://smart-riego.netlify.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(productos.router)
app.include_router(pedidos.router)
app.include_router(dispositivos.router)
app.include_router(equipo.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    productos_en_base = db.execute(text("SELECT COUNT(*) FROM productos")).scalar()
    return {"estado": "ok", "productos_en_base": productos_en_base}