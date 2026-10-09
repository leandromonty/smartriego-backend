import hashlib
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Comando, Dispositivo, Lectura
from ..schemas import ActivarIn, ActivarOut, LecturaIn, LecturaRespuesta

router = APIRouter(prefix="/equipo", tags=["equipo (Arduino/ESP32)"])


def _hash(clave: str) -> str:
    # La clave es aleatoria y larga, por eso alcanza con SHA-256 (no hace falta Argon2)
    return hashlib.sha256(clave.encode()).hexdigest()


def dispositivo_autenticado(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Dispositivo:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Falta la API key del equipo")
    dispositivo = db.scalar(
        select(Dispositivo).where(Dispositivo.api_key_hash == _hash(x_api_key))
    )
    if dispositivo is None:
        raise HTTPException(status_code=401, detail="API key inválida")
    return dispositivo


@router.post("/activar", response_model=ActivarOut)
def activar(datos: ActivarIn, db: Session = Depends(get_db)):
    """El equipo canjea su código de activación por una API key. Se hace una sola vez."""
    codigo = datos.codigo_activacion.strip().upper()
    dispositivo = db.scalar(
        select(Dispositivo).where(Dispositivo.codigo_activacion == codigo).with_for_update()
    )
    if dispositivo is None:
        raise HTTPException(status_code=404, detail="Código de activación inválido")
    if dispositivo.api_key_hash is not None:
        raise HTTPException(status_code=409, detail="Este equipo ya fue activado")

    clave = secrets.token_urlsafe(32)
    dispositivo.api_key_hash = _hash(clave)  # solo se guarda el hash
    dispositivo.activado_en = func.now()
    dispositivo_id = dispositivo.id
    umbral = dispositivo.umbral_humedad
    db.commit()

    # La clave en texto plano se devuelve UNA vez y no se puede volver a consultar
    return ActivarOut(api_key=clave, dispositivo_id=dispositivo_id, umbral_humedad=umbral)


@router.post("/lecturas", response_model=LecturaRespuesta)
def recibir_lectura(
    datos: LecturaIn,
    dispositivo: Dispositivo = Depends(dispositivo_autenticado),
    db: Session = Depends(get_db),
):
    """El equipo manda su lectura y recibe si tiene que hacer un riego manual."""
    dispositivo_id = dispositivo.id
    umbral = dispositivo.umbral_humedad

    db.add(
        Lectura(
            dispositivo_id=dispositivo_id,
            humedad=datos.humedad,
            deposito_bajo=datos.deposito_bajo,
            bomba_activa=datos.bomba_activa,
        )
    )

    # Marca como ejecutados todos los comandos pendientes, en un solo paso
    resultado = db.execute(
        update(Comando)
        .where(Comando.dispositivo_id == dispositivo_id, Comando.estado == "pendiente")
        .values(estado="ejecutado", ejecutado_en=func.now())
    )
    riego_manual = resultado.rowcount > 0
    db.commit()

    return LecturaRespuesta(riego_manual=riego_manual, umbral_humedad=umbral)