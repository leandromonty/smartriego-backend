from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Dispositivo, Usuario
from ..schemas import DispositivoOut
from ..security import usuario_actual

router = APIRouter(prefix="/dispositivos", tags=["dispositivos"])


@router.get("", response_model=list[DispositivoOut])
def mis_dispositivos(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    consulta = (
        select(Dispositivo)
        .where(Dispositivo.usuario_id == usuario.id)
        .options(selectinload(Dispositivo.producto))
        .order_by(Dispositivo.id)
    )
    return db.scalars(consulta).all()