from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Producto
from ..schemas import ProductoOut

router = APIRouter(prefix="/productos", tags=["productos"])


@router.get("", response_model=list[ProductoOut])
def listar(db: Session = Depends(get_db)):
    consulta = select(Producto).where(Producto.activo.is_(True)).order_by(Producto.id)
    return db.scalars(consulta).all()