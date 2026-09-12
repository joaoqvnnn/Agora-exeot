# ============================================
# 📦 STOCK SERVICE — Larizinha Store
# ============================================
# Regras de negócio do estoque (logins individuais).
# Reserva, entrega, vencimento, remoção, consulta.
# ============================================

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Product, StockItem, StockStatus


# ============================================
# 📊 CONSULTAS
# ============================================
async def count_available(
    session: AsyncSession,
    product_id: int,
) -> int:
    """Conta unidades disponíveis de um produto."""
    stmt = select(func.count(StockItem.id)).where(
        StockItem.product_id == product_id,
        StockItem.status == StockStatus.AVAILABLE,
    )
    return await session.scalar(stmt) or 0


async def count_all_by_status(
    session: AsyncSession,
    product_id: int,
) -> dict[str, int]:
    """Retorna contagem por status de um produto."""
    stmt = (
        select(StockItem.status, func.count(StockItem.id))
        .where(StockItem.product_id == product_id)
        .group_by(StockItem.status)
    )
    result = await session.execute(stmt)
    counts = {s.value: 0 for s in StockStatus}
    for status, count in result.all():
        counts[status.value] = count
    return counts


async def count_total_stock(session: AsyncSession) -> int:
    """Conta estoque total disponível (todos os produtos)."""
    stmt = select(func.count(StockItem.id)).where(
        StockItem.status == StockStatus.AVAILABLE,
    )
    return await session.scalar(stmt) or 0


async def count_by_product_summary(
    session: AsyncSession,
) -> list[dict]:
    """Resumo de estoque por produto (pra painel admin)."""
    stmt = (
        select(
            Product.id,
            Product.name,
            func.count(StockItem.id).label("total"),
        )
        .join(StockItem, StockItem.product_id == Product.id, isouter=True)
        .where(StockItem.status == StockStatus.AVAILABLE)
        .group_by(Product.id, Product.name)
        .order_by(Product.name)
    )
    result = await session.execute(stmt)
    return [
        {"product_id": r.id, "product_name": r.name, "available": r.total}
        for r in result.all()
    ]


# ============================================
# 🔓 RESERVA
# ============================================
async def reserve_items(
    session: AsyncSession,
    product_id: int,
    quantity: int,
    user_telegram_id: int,
    reserve_minutes: int = 15,
) -> list[StockItem]:
    """
    Reserva N unidades disponíveis por X minutos.
    Retorna a lista reservada. Se não tiver estoque suficiente,
    retorna lista vazia.
    """
    if quantity <= 0:
        return []

    stmt = (
        select(StockItem)
        .where(
            StockItem.product_id == product_id,
            StockItem.status == StockStatus.AVAILABLE,
        )
        .order_by(StockItem.id)
        .limit(quantity)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    if len(items) < quantity:
        # Não tem estoque suficiente — desfaz nada
        return []

    reserved_until = datetime.now(timezone.utc) + timedelta(minutes=reserve_minutes)
    for item in items:
        item.status = StockStatus.RESERVED
        item.reserved_by = user_telegram_id
        item.reserved_until = reserved_until
        session.add(item)

    await session.flush()
    logger.info(
        f"🔒 Reservado {len(items)} item(ns) do produto {product_id} "
        f"para usuário {user_telegram_id}"
    )
    return items


async def release_reservation(
    session: AsyncSession,
    user_telegram_id: int,
    product_id: Optional[int] = None,
) -> int:
    """Libera reservas do usuário (volta pra disponível)."""
    stmt = select(StockItem).where(
        StockItem.status == StockStatus.RESERVED,
        StockItem.reserved_by == user_telegram_id,
    )
    if product_id is not None:
        stmt = stmt.where(StockItem.product_id == product_id)

    result = await session.execute(stmt)
    items = list(result.scalars().all())

    for item in items:
        item.status = StockStatus.AVAILABLE
        item.reserved_by = None
        item.reserved_until = None
        session.add(item)

    await session.flush()
    if items:
        logger.info(f"🔓 Liberado {len(items)} item(ns) do usuário {user_telegram_id}")
    return len(items)


async def release_expired_reservations(session: AsyncSession) -> int:
    """Libera reservas vencidas (roda no cron)."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(StockItem)
        .where(
            StockItem.status == StockStatus.RESERVED,
            StockItem.reserved_until < now,
        )
        .values(
            status=StockStatus.AVAILABLE,
            reserved_by=None,
            reserved_until=None,
        )
    )
    result = await session.execute(stmt)
    count = result.rowcount or 0
    if count:
        logger.info(f"⏰ Liberadas {count} reservas vencidas")
    return count


# ============================================
# 💰 VENDA / ENTREGA
# ============================================
async def mark_as_sold(
    session: AsyncSession,
    item_ids: list[int],
    user_telegram_id: int,
    order_id: int,
    duration_days: int,
) -> list[StockItem]:
    """Marca itens como vendidos e vincula ao pedido."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=duration_days)

    stmt = select(StockItem).where(StockItem.id.in_(item_ids))
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    for item in items:
        item.status = StockStatus.SOLD
        item.sold_to = user_telegram_id
        item.order_id = order_id
        item.sold_at = now
        item.expires_at = expires_at
        item.reserved_by = None
        item.reserved_until = None
        session.add(item)

    await session.flush()
    logger.info(
        f"💎 Vendido {len(items)} item(ns) pra {user_telegram_id} "
        f"(pedido {order_id})"
    )
    return items


async def mark_as_delivered(
    session: AsyncSession,
    item_ids: list[int],
) -> int:
    """Marca itens como entregues."""
    stmt = (
        update(StockItem)
        .where(StockItem.id.in_(item_ids))
        .values(status=StockStatus.DELIVERED)
    )
    result = await session.execute(stmt)
    return result.rowcount or 0


async def mark_expired(session: AsyncSession) -> int:
    """Marca como expirado itens vendidos que venceram."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(StockItem)
        .where(
            StockItem.status.in_([StockStatus.SOLD, StockStatus.DELIVERED]),
            StockItem.expires_at.is_not(None),
            StockItem.expires_at < now,
        )
        .values(status=StockStatus.EXPIRED)
    )
    result = await session.execute(stmt)
    count = result.rowcount or 0
    if count:
        logger.info(f"⌛ {count} logins expirados")
    return count


async def get_user_active_items(
    session: AsyncSession,
    user_telegram_id: int,
) -> list[StockItem]:
    """Retorna itens ativos (não vencidos) do usuário."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(StockItem)
        .where(
            StockItem.sold_to == user_telegram_id,
            StockItem.status.in_([StockStatus.SOLD, StockStatus.DELIVERED]),
            StockItem.expires_at.is_not(None),
            StockItem.expires_at > now,
        )
        .order_by(StockItem.sold_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ============================================
# ➕ ADIÇÃO (painel admin)
# ============================================
async def add_stock_item(
    session: AsyncSession,
    product_id: int,
    email: Optional[str] = None,
    password: Optional[str] = None,
    code: Optional[str] = None,
    note: Optional[str] = None,
    extra_data: Optional[dict] = None,
) -> StockItem:
    """Adiciona uma unidade de estoque."""
    item = StockItem(
        product_id=product_id,
        email=email,
        password=password,
        code=code,
        note=note,
        extra_data=extra_data or {},
        status=StockStatus.AVAILABLE,
    )
    session.add(item)
    await session.flush()
    return item


async def add_stock_bulk(
    session: AsyncSession,
    product_id: int,
    lines: list[str],
    separator: str = "===",
) -> int:
    """
    Adiciona várias unidades de uma vez.
    Formato de cada linha:
      EMAIL===SENHA===CODIGO===NOTA
    Campos vazios podem ser deixados em branco.
    Retorna quantidade adicionada.
    """
    added = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(separator)]
        while len(parts) < 4:
            parts.append("")

        email, password, code, note = parts[0], parts[1], parts[2], parts[3]

        if not any([email, password, code]):
            continue

        await add_stock_item(
            session=session,
            product_id=product_id,
            email=email or None,
            password=password or None,
            code=code or None,
            note=note or None,
        )
        added += 1

    logger.info(f"➕ Adicionados {added} logins ao produto {product_id}")
    return added


# ============================================
# ➖ REMOÇÃO (painel admin)
# ============================================
async def remove_by_email(
    session: AsyncSession,
    product_id: int,
    email: str,
) -> int:
    """Remove unidades disponíveis por e-mail."""
    stmt = select(StockItem).where(
        StockItem.product_id == product_id,
        StockItem.email == email,
        StockItem.status == StockStatus.AVAILABLE,
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())
    for item in items:
        await session.delete(item)
    return len(items)


async def remove_all_by_product(
    session: AsyncSession,
    product_id: int,
    only_available: bool = True,
) -> int:
    """Remove todo o estoque de um produto."""
    stmt = select(StockItem).where(StockItem.product_id == product_id)
    if only_available:
        stmt = stmt.where(StockItem.status == StockStatus.AVAILABLE)

    result = await session.execute(stmt)
    items = list(result.scalars().all())
    for item in items:
        await session.delete(item)
    logger.warning(f"🗑️ Removidos {len(items)} itens do produto {product_id}")
    return len(items)


async def clear_all_stock(session: AsyncSession) -> int:
    """Zera TODO o estoque disponível."""
    stmt = select(StockItem).where(StockItem.status == StockStatus.AVAILABLE)
    result = await session.execute(stmt)
    items = list(result.scalars().all())
    for item in items:
        await session.delete(item)
    logger.warning(f"🗑️ Estoque zerado: {len(items)} itens removidos")
    return len(items)


async def remove_by_product_name(
    session: AsyncSession,
    product_name: str,
) -> int:
    """Remove estoque pelo nome do produto (busca exata)."""
    stmt = select(Product).where(Product.name == product_name)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        return 0
    return await remove_all_by_product(session, product.id, only_available=True)


# ============================================
# 💵 ALTERAÇÃO DE PREÇO
# ============================================
async def change_product_price(
    session: AsyncSession,
    product_name: str,
    new_price: Decimal,
) -> bool:
    """Altera o preço de um produto específico."""
    stmt = select(Product).where(Product.name == product_name)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        return False
    product.price = new_price
    session.add(product)
    return True


async def change_all_prices(
    session: AsyncSession,
    new_price: Decimal,
) -> int:
    """Altera o preço de TODOS os produtos."""
    stmt = select(Product)
    result = await session.execute(stmt)
    products = list(result.scalars().all())
    for p in products:
        p.price = new_price
        session.add(p)
    logger.warning(f"💵 Preço de {len(products)} produtos alterado para {new_price}")
    return len(products)


# ============================================
# 📋 LISTAGEM DETALHADA
# ============================================
async def list_stock_by_product(
    session: AsyncSession,
    product_id: int,
    status: Optional[StockStatus] = None,
    limit: int = 50,
) -> list[StockItem]:
    """Lista itens de um produto (pra painel admin)."""
    stmt = select(StockItem).where(StockItem.product_id == product_id)
    if status is not None:
        stmt = stmt.where(StockItem.status == status)
    stmt = stmt.order_by(StockItem.id.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
