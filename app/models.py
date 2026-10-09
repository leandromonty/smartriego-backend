from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(Enum("cliente", "admin"), default="cliente")
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(255))
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    estado: Mapped[str] = mapped_column(
        Enum("pendiente", "pagado", "enviado", "entregado", "cancelado"),
        default="pendiente",
    )
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())

    items: Mapped[list["PedidoItem"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )


class PedidoItem(Base):
    __tablename__ = "pedido_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad: Mapped[int]
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    pedido: Mapped["Pedido"] = relationship(back_populates="items")
    producto: Mapped["Producto"] = relationship()


class Dispositivo(Base):
    __tablename__ = "dispositivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    nombre: Mapped[str] = mapped_column(String(100), default="Mi SmartRiego")
    codigo_activacion: Mapped[str] = mapped_column(String(20), unique=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(255))
    umbral_humedad: Mapped[int] = mapped_column(default=30)
    activado_en: Mapped[datetime | None]
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())

    producto: Mapped["Producto"] = relationship()


class Lectura(Base):
    __tablename__ = "lecturas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dispositivo_id: Mapped[int] = mapped_column(ForeignKey("dispositivos.id"))
    humedad: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    deposito_bajo: Mapped[bool] = mapped_column(Boolean, default=False)
    bomba_activa: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())


class Comando(Base):
    __tablename__ = "comandos"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispositivo_id: Mapped[int] = mapped_column(ForeignKey("dispositivos.id"))
    tipo: Mapped[str] = mapped_column(Enum("riego_manual"), default="riego_manual")
    estado: Mapped[str] = mapped_column(Enum("pendiente", "ejecutado"), default="pendiente")
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())
    ejecutado_en: Mapped[datetime | None]