from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from ..schemas import LoginIn, RegistroIn, TokenOut, UsuarioOut
from ..security import crear_token, hashear, usuario_actual, verificar

router = APIRouter(prefix="/auth", tags=["auth"])


def _respuesta_token(usuario: Usuario) -> TokenOut:
    return TokenOut(
        access_token=crear_token(usuario.id),
        usuario=UsuarioOut.model_validate(usuario),
    )


@router.post("/registro", response_model=TokenOut, status_code=201)
def registro(datos: RegistroIn, db: Session = Depends(get_db)):
    email = datos.email.lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese email")

    usuario = Usuario(
        nombre=datos.nombre.strip(),
        email=email,
        password_hash=hashear(datos.password),
        # el rol nunca viene del cliente: todo registro nace como "cliente"
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return _respuesta_token(usuario)


@router.post("/login", response_model=TokenOut)
def login(datos: LoginIn, db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == datos.email.lower()))
    if usuario is None or not verificar(datos.password, usuario.password_hash):
        # mismo mensaje en ambos casos, para no revelar qué emails existen
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    return _respuesta_token(usuario)


@router.get("/me", response_model=UsuarioOut)
def me(usuario: Usuario = Depends(usuario_actual)):
    return usuario