from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegistroIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    email: str
    rol: str
    creado_en: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


class ProductoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    nombre: str
    descripcion: str | None
    precio: float


class ItemIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    cantidad: int = Field(ge=1, le=20)


class PedidoIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1, max_length=10)


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    producto: ProductoOut
    cantidad: int
    precio_unitario: float


class PedidoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    total: float
    estado: str
    creado_en: datetime
    items: list[ItemOut]


class DispositivoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    codigo_activacion: str
    umbral_humedad: int
    activado_en: datetime | None
    creado_en: datetime
    producto: ProductoOut


class PagoOut(BaseModel):
    pedido: PedidoOut
    dispositivos: list[DispositivoOut]