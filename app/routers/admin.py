"""Panel de administración: todo lo de /admin exige rol "admin" (se controla acá, en el servidor)."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Dispositivo, Lectura, Pedido, PedidoItem, Producto, Usuario
from ..schemas import ItemOut
from ..security import solo_admin
from .pedidos import _codigo_activacion

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(solo_admin)])

ESTADOS = ("pendiente", "pagado", "enviado", "entregado", "cancelado")
ESTADOS_COBRADOS = ("pagado", "enviado", "entregado")

# Desde qué estado se puede pasar a cuál
TRANSICIONES = {
    "pendiente": {"pagado", "cancelado"},
    "pagado": {"enviado", "entregado", "cancelado"},
    "enviado": {"entregado", "cancelado"},
    "entregado": set(),
    "cancelado": set(),
}

# Un equipo se considera conectado si mandó una lectura en el último minuto
SEGUNDOS_CONECTADO = 60


# ---------- Respuestas ----------
class ResumenOut(BaseModel):
    clientes: int
    pedidos: int
    pedidos_por_estado: dict[str, int]
    ingresos: float
    equipos: int
    equipos_activados: int
    equipos_conectados: int


class AdminPedidoOut(BaseModel):
    id: int
    usuario_nombre: str
    usuario_email: str
    total: float
    estado: str
    creado_en: datetime
    items: list[ItemOut]
    equipos: int
    equipos_activados: int


class AdminDispositivoOut(BaseModel):
    id: int
    nombre: str
    codigo_activacion: str
    producto_nombre: str
    usuario_nombre: str
    usuario_email: str
    activado_en: datetime | None
    ultima_lectura_en: datetime | None
    humedad: float | None
    deposito_bajo: bool | None
    conectado: bool


class AdminUsuarioOut(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    avatar: str
    creado_en: datetime
    pedidos: int
    equipos: int


class AdminProductoOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None
    precio: float
    activo: bool


# ---------- Entradas ----------
class EstadoIn(BaseModel):
    estado: Literal["pendiente", "pagado", "enviado", "entregado", "cancelado"]


class ProductoAdminIn(BaseModel):
    precio: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    activo: bool | None = None
    descripcion: str | None = Field(default=None, max_length=255)


# ---------- Utilidades ----------
def _ahora_db(db: Session) -> datetime:
    # Se usa la hora de la base de datos, la misma con la que se guardan las lecturas
    return db.scalar(select(func.now()))


def _cargar_pedido(db: Session, pedido_id: int, bloquear: bool = False) -> Pedido:
    consulta = (
        select(Pedido)
        .where(Pedido.id == pedido_id)
        .options(selectinload(Pedido.items).selectinload(PedidoItem.producto))
    )
    if bloquear:
        consulta = consulta.with_for_update()
    pedido = db.scalar(consulta)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return pedido


def _armar_pedido(db: Session, pedido: Pedido) -> AdminPedidoOut:
    usuario = db.get(Usuario, pedido.usuario_id)
    total, activados = db.execute(
        select(func.count(), func.count(Dispositivo.api_key_hash)).where(
            Dispositivo.pedido_id == pedido.id
        )
    ).one()
    return AdminPedidoOut(
        id=pedido.id,
        usuario_nombre=usuario.nombre,
        usuario_email=usuario.email,
        total=pedido.total,
        estado=pedido.estado,
        creado_en=pedido.creado_en,
        items=[ItemOut.model_validate(i) for i in pedido.items],
        equipos=total,
        equipos_activados=activados,
    )


# ---------- Resumen ----------
@router.get("/resumen", response_model=ResumenOut)
def resumen(db: Session = Depends(get_db)):
    por_estado = {estado: 0 for estado in ESTADOS}
    for estado, cantidad in db.execute(select(Pedido.estado, func.count()).group_by(Pedido.estado)):
        por_estado[estado] = cantidad

    ingresos = db.scalar(
        select(func.coalesce(func.sum(Pedido.total), 0)).where(Pedido.estado.in_(ESTADOS_COBRADOS))
    )
    clientes = db.scalar(select(func.count()).select_from(Usuario).where(Usuario.rol == "cliente"))
    equipos = db.scalar(select(func.count()).select_from(Dispositivo))
    activados = db.scalar(select(func.count(Dispositivo.api_key_hash)))

    desde = _ahora_db(db) - timedelta(seconds=SEGUNDOS_CONECTADO)
    conectados = db.scalar(
        select(func.count(func.distinct(Lectura.dispositivo_id))).where(Lectura.creado_en >= desde)
    )

    return ResumenOut(
        clientes=clientes,
        pedidos=sum(por_estado.values()),
        pedidos_por_estado=por_estado,
        ingresos=ingresos,
        equipos=equipos,
        equipos_activados=activados,
        equipos_conectados=conectados,
    )


# ---------- Pedidos ----------
@router.get("/pedidos", response_model=list[AdminPedidoOut])
def listar_pedidos(estado: str | None = Query(default=None), db: Session = Depends(get_db)):
    if estado is not None and estado not in ESTADOS:
        raise HTTPException(status_code=400, detail="Estado inválido")

    consulta = (
        select(Pedido, Usuario)
        .join(Usuario, Usuario.id == Pedido.usuario_id)
        .options(selectinload(Pedido.items).selectinload(PedidoItem.producto))
        .order_by(Pedido.id.desc())
    )
    if estado:
        consulta = consulta.where(Pedido.estado == estado)
    filas = db.execute(consulta).all()

    equipos: dict[int, tuple[int, int]] = {}
    ids = [pedido.id for pedido, _ in filas]
    if ids:
        for pedido_id, total, activados in db.execute(
            select(Dispositivo.pedido_id, func.count(), func.count(Dispositivo.api_key_hash))
            .where(Dispositivo.pedido_id.in_(ids))
            .group_by(Dispositivo.pedido_id)
        ):
            equipos[pedido_id] = (total, activados)

    return [
        AdminPedidoOut(
            id=pedido.id,
            usuario_nombre=usuario.nombre,
            usuario_email=usuario.email,
            total=pedido.total,
            estado=pedido.estado,
            creado_en=pedido.creado_en,
            items=[ItemOut.model_validate(i) for i in pedido.items],
            equipos=equipos.get(pedido.id, (0, 0))[0],
            equipos_activados=equipos.get(pedido.id, (0, 0))[1],
        )
        for pedido, usuario in filas
    ]


@router.patch("/pedidos/{pedido_id}", response_model=AdminPedidoOut)
def cambiar_estado(pedido_id: int, datos: EstadoIn, db: Session = Depends(get_db)):
    pedido = _cargar_pedido(db, pedido_id, bloquear=True)
    nuevo = datos.estado

    if nuevo == pedido.estado:
        return _armar_pedido(db, pedido)
    if nuevo not in TRANSICIONES[pedido.estado]:
        raise HTTPException(
            status_code=409, detail=f"No se puede pasar de «{pedido.estado}» a «{nuevo}»"
        )

    dispositivos = db.scalars(select(Dispositivo).where(Dispositivo.pedido_id == pedido_id)).all()

    if nuevo == "cancelado":
        if any(d.api_key_hash for d in dispositivos):
            raise HTTPException(
                status_code=409,
                detail="El pedido tiene equipos ya activados: no se puede cancelar",
            )
        # Los códigos de activación de un pedido cancelado dejan de existir
        for d in dispositivos:
            db.delete(d)

    if nuevo == "pagado" and not dispositivos:
        # Igual que un pago normal: un equipo por cada unidad comprada
        usados: set[str] = set()
        for item in pedido.items:
            for _ in range(item.cantidad):
                db.add(
                    Dispositivo(
                        usuario_id=pedido.usuario_id,
                        pedido_id=pedido.id,
                        producto_id=item.producto_id,
                        codigo_activacion=_codigo_activacion(db, usados),
                    )
                )

    pedido.estado = nuevo
    db.commit()
    return _armar_pedido(db, _cargar_pedido(db, pedido_id))


@router.delete("/pedidos/{pedido_id}", status_code=204)
def eliminar_pedido(pedido_id: int, db: Session = Depends(get_db)):
    pedido = _cargar_pedido(db, pedido_id, bloquear=True)
    if pedido.estado != "cancelado":
        raise HTTPException(status_code=409, detail="Solo se pueden eliminar pedidos cancelados")
    tiene_equipos = db.scalar(
        select(func.count()).select_from(Dispositivo).where(Dispositivo.pedido_id == pedido_id)
    )
    if tiene_equipos:
        raise HTTPException(status_code=409, detail="El pedido todavía tiene equipos asociados")
    db.delete(pedido)
    db.commit()


# ---------- Equipos ----------
@router.get("/dispositivos", response_model=list[AdminDispositivoOut])
def listar_dispositivos(db: Session = Depends(get_db)):
    ultima = (
        select(Lectura.dispositivo_id, func.max(Lectura.id).label("lectura_id"))
        .group_by(Lectura.dispositivo_id)
        .subquery()
    )
    filas = db.execute(
        select(Dispositivo, Usuario, Producto, Lectura)
        .join(Usuario, Usuario.id == Dispositivo.usuario_id)
        .join(Producto, Producto.id == Dispositivo.producto_id)
        .outerjoin(ultima, ultima.c.dispositivo_id == Dispositivo.id)
        .outerjoin(Lectura, Lectura.id == ultima.c.lectura_id)
        .order_by(Dispositivo.id.desc())
    ).all()

    ahora = _ahora_db(db)
    limite = timedelta(seconds=SEGUNDOS_CONECTADO)
    return [
        AdminDispositivoOut(
            id=d.id,
            nombre=d.nombre,
            codigo_activacion=d.codigo_activacion,
            producto_nombre=p.nombre,
            usuario_nombre=u.nombre,
            usuario_email=u.email,
            activado_en=d.activado_en,
            ultima_lectura_en=l.creado_en if l else None,
            humedad=l.humedad if l else None,
            deposito_bajo=l.deposito_bajo if l else None,
            conectado=bool(l and ahora - l.creado_en <= limite),
        )
        for d, u, p, l in filas
    ]


# ---------- Usuarios ----------
@router.get("/usuarios", response_model=list[AdminUsuarioOut])
def listar_usuarios(db: Session = Depends(get_db)):
    pedidos = dict(db.execute(select(Pedido.usuario_id, func.count()).group_by(Pedido.usuario_id)).all())
    equipos = dict(
        db.execute(select(Dispositivo.usuario_id, func.count()).group_by(Dispositivo.usuario_id)).all()
    )
    usuarios = db.scalars(select(Usuario).order_by(Usuario.id)).all()
    return [
        AdminUsuarioOut(
            id=u.id,
            nombre=u.nombre,
            email=u.email,
            rol=u.rol,
            avatar=u.avatar,
            creado_en=u.creado_en,
            pedidos=pedidos.get(u.id, 0),
            equipos=equipos.get(u.id, 0),
        )
        for u in usuarios
    ]


# ---------- Productos ----------
@router.get("/productos", response_model=list[AdminProductoOut])
def listar_productos(db: Session = Depends(get_db)):
    return db.scalars(select(Producto).order_by(Producto.id)).all()


@router.patch("/productos/{producto_id}", response_model=AdminProductoOut)
def editar_producto(producto_id: int, datos: ProductoAdminIn, db: Session = Depends(get_db)):
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    # Solo cambia lo que viene en el pedido; los pedidos ya hechos conservan su precio
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(producto, campo, valor)
    db.commit()
    db.refresh(producto)
    return producto
