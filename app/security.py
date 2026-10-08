from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Usuario

_hasher = PasswordHash.recommended()  # Argon2
bearer = HTTPBearer(auto_error=False)


def hashear(password: str) -> str:
    return _hasher.hash(password)


def verificar(password: str, hash_guardado: str) -> bool:
    return _hasher.verify(password, hash_guardado)


def crear_token(usuario_id: int) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode(
        {"sub": str(usuario_id), "exp": expira},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    error = HTTPException(
        status_code=401,
        detail="Token inválido o vencido",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credenciales is None:
        raise error
    try:
        datos = jwt.decode(
            credenciales.credentials, settings.secret_key, algorithms=[settings.algorithm]
        )
        usuario_id = int(datos["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise error

    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise error
    return usuario


def solo_admin(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Requiere rol de administrador")
    return usuario