from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Comando, Dispositivo, Lectura, Usuario
from ..schemas import DispositivoOut, LecturaApp, RegistroApp
from ..security import usuario_actual

router = APIRouter(prefix="/dispositivos", tags=["dispositivos"])


def _del_usuario(db: Session, dispositivo_id: int, usuario: Usuario) -> Dispositivo:
    dispositivo = db.scalar(
        select(Dispositivo).where(
            Dispositivo.id == dispositivo_id, Dispositivo.usuario_id == usuario.id
        )
    )
    if dispositivo is None:
        # 404 también si es de otro usuario: no revelamos que existe
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return dispositivo


def _ultima_lectura(db: Session, dispositivo_id: int) -> Lectura | None:
    return db.scalar(
        select(Lectura)
        .where(Lectura.dispositivo_id == dispositivo_id)
        .order_by(Lectura.id.desc())
        .limit(1)
    )


def _hay_comando_pendiente(db: Session, dispositivo_id: int) -> bool:
    return (
        db.scalar(
            select(Comando.id)
            .where(Comando.dispositivo_id == dispositivo_id, Comando.estado == "pendiente")
            .limit(1)
        )
        is not None
    )


def _a_lectura_app(lectura: Lectura, riego_pendiente: bool) -> LecturaApp:
    return LecturaApp(
        humedad=round(lectura.humedad),
        bomba_encendida=lectura.bomba_activa,
        deposito_bajo=lectura.deposito_bajo,
        riego_pendiente=riego_pendiente,
    )


@router.get("", response_model=list[DispositivoOut])
def mis_dispositivos(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    consulta = (
        select(Dispositivo)
        .where(Dispositivo.usuario_id == usuario.id)
        .options(selectinload(Dispositivo.producto))
        .order_by(Dispositivo.id)
    )
    return db.scalars(consulta).all()


@router.get("/{dispositivo_id}/lectura/ultima", response_model=LecturaApp)
def ultima(dispositivo_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    _del_usuario(db, dispositivo_id, usuario)
    lectura = _ultima_lectura(db, dispositivo_id)
    if lectura is None:
        raise HTTPException(status_code=404, detail="Todavía no hay lecturas de este equipo")
    return _a_lectura_app(lectura, _hay_comando_pendiente(db, dispositivo_id))


@router.get("/{dispositivo_id}/lectura/historial", response_model=list[RegistroApp])
def historial(dispositivo_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    _del_usuario(db, dispositivo_id, usuario)
    filas = db.scalars(
        select(Lectura)
        .where(Lectura.dispositivo_id == dispositivo_id)
        .order_by(Lectura.id.desc())
        .limit(30)
    ).all()
    # Se leyeron de la más nueva a la más vieja; el gráfico las quiere en orden cronológico
    return [
        RegistroApp(humedad=round(f.humedad), hora=f.creado_en.strftime("%H:%M:%S"))
        for f in reversed(filas)
    ]


@router.post("/{dispositivo_id}/riego/manual", response_model=LecturaApp)
def riego_manual(dispositivo_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    _del_usuario(db, dispositivo_id, usuario)
    lectura = _ultima_lectura(db, dispositivo_id)
    if lectura is None:
        raise HTTPException(
            status_code=409,
            detail="El equipo todavía no envió lecturas. ¿Está activado y encendido?",
        )

    # Si ya hay un riego esperando al equipo, no se duplica
    if not _hay_comando_pendiente(db, dispositivo_id):
        db.add(Comando(dispositivo_id=dispositivo_id))

    respuesta = _a_lectura_app(lectura, riego_pendiente=True)
    db.commit()
    return respuesta