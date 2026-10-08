import secrets
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Dispositivo, Pedido, PedidoItem, Producto, Usuario
from ..schemas import DispositivoOut, PagoOut, PedidoIn, PedidoOut
from ..security import usuario_actual

router = APIRouter(prefix="/pedidos", tags=["pedidos"])

# Sin 0/O ni 1/I para que el código sea fácil de leer y copiar
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _consulta_pedidos():
    return select(Pedido).options(
        selectinload(Pedido.items).selectinload(PedidoItem.producto)
    )


def _obtener_pedido(db: Session, pedido_id: int, usuario: Usuario, bloquear: bool = False):
    consulta = _consulta_pedidos().where(
        Pedido.id == pedido_id, Pedido.usuario_id == usuario.id
    )
    if bloquear:
        consulta = consulta.with_for_update()  # evita pagar dos veces el mismo pedido
    pedido = db.scalar(consulta)
    if pedido is None:
        # 404 también si el pedido es de otro usuario: no revelamos que existe
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return pedido


def _codigo_activacion(db: Session, usados: set[str]) -> str:
    while True:
        parte1 = "".join(secrets.choice(ALFABETO) for _ in range(4))
        parte2 = "".join(secrets.choice(ALFABETO) for _ in range(4))
        codigo = f"SR-{parte1}-{parte2}"
        existe = db.scalar(select(Dispositivo.id).where(Dispositivo.codigo_activacion == codigo))
        if codigo not in usados and existe is None:
            usados.add(codigo)
            return codigo


@router.post("", response_model=PedidoOut, status_code=201)
def crear(datos: PedidoIn, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    # Si el mismo producto viene repetido, se suman las cantidades
    cantidades: dict[str, int] = {}
    for item in datos.items:
        cantidades[item.codigo] = cantidades.get(item.codigo, 0) + item.cantidad

    if any(cantidad > 20 for cantidad in cantidades.values()):
        raise HTTPException(status_code=400, detail="Máximo 20 unidades por producto")

    productos = db.scalars(
        select(Producto).where(Producto.codigo.in_(cantidades), Producto.activo.is_(True))
    ).all()
    por_codigo = {p.codigo: p for p in productos}

    faltantes = [codigo for codigo in cantidades if codigo not in por_codigo]
    if faltantes:
        raise HTTPException(status_code=400, detail=f"Producto inexistente: {', '.join(faltantes)}")

    pedido = Pedido(usuario_id=usuario.id, total=Decimal("0"))
    total = Decimal("0")
    for codigo, cantidad in cantidades.items():
        producto = por_codigo[codigo]
        pedido.items.append(
            PedidoItem(
                producto_id=producto.id,
                cantidad=cantidad,
                precio_unitario=producto.precio,  # precio congelado al comprar
            )
        )
        total += producto.precio * cantidad
    pedido.total = total

    db.add(pedido)
    db.commit()

    consulta = _consulta_pedidos().where(Pedido.id == pedido.id)
    return db.scalar(consulta.execution_options(populate_existing=True))


@router.get("", response_model=list[PedidoOut])
def mis_pedidos(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    consulta = (
        _consulta_pedidos().where(Pedido.usuario_id == usuario.id).order_by(Pedido.id.desc())
    )
    return db.scalars(consulta).all()


@router.get("/{pedido_id}", response_model=PedidoOut)
def ver_pedido(pedido_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    return _obtener_pedido(db, pedido_id, usuario)


@router.post("/{pedido_id}/pagar", response_model=PagoOut)
def pagar(pedido_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    pedido = _obtener_pedido(db, pedido_id, usuario, bloquear=True)

    if pedido.estado != "pendiente":
        raise HTTPException(status_code=409, detail="El pedido ya no está pendiente")

    # PLACEHOLDER: acá se integraría la pasarela de pago real (Mercado Pago).
    # Por ahora el pago se da por aprobado.
    pedido.estado = "pagado"

    # Un dispositivo por cada unidad comprada, vinculado a la cuenta del cliente
    usados: set[str] = set()
    for item in pedido.items:
        for _ in range(item.cantidad):
            db.add(
                Dispositivo(
                    usuario_id=usuario.id,
                    pedido_id=pedido.id,
                    producto_id=item.producto_id,
                    codigo_activacion=_codigo_activacion(db, usados),
                )
            )
    db.commit()

    pedido = db.scalar(
        _consulta_pedidos().where(Pedido.id == pedido_id).execution_options(populate_existing=True)
    )
    dispositivos = db.scalars(
        select(Dispositivo)
        .where(Dispositivo.pedido_id == pedido_id)
        .options(selectinload(Dispositivo.producto))
        .order_by(Dispositivo.id)
    ).all()

    return PagoOut(
        pedido=PedidoOut.model_validate(pedido),
        dispositivos=[DispositivoOut.model_validate(d) for d in dispositivos],
    )