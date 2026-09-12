# ============================================
# 🌐 WEBAPP ROUTES — Larizinha Store
# ============================================
# Backend completo do Mini App (Telegram WebApp).
#
# Responsabilidades:
#   - Autenticar via Telegram initData (HMAC)
#   - Retornar catálogo (produtos + categorias)
#   - Retornar dados do usuário (saldo, pontos)
#   - Criar/validar pedido (checkout)
#   - Criar Pix para recarga
#   - Retornar histórico
#
# Rotas:
#   POST /api/webapp/auth          → valida initData, retorna token
#   GET  /api/webapp/me            → dados do usuário logado
#   GET  /api/webapp/catalog       → categorias + produtos
#   GET  /api/webapp/product/{id}  → detalhes de um produto
#   POST /api/webapp/checkout      → finaliza compra
#   POST /api/webapp/recharge      → cria Pix
#   GET  /api/webapp/payment/{id}  → status do Pix
#   GET  /api/webapp/history       → histórico de compras
#   GET  /api/webapp/config        → cores, textos, logo
# ============================================

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from core.models import (
    Category,
    Order,
    OrderStatus,
    Product,
    ProductStatus,
    StockItem,
    StockStatus,
    User,
    UserStatus,
)
from core.services import config as config_service
from core.services import payment as payment_service
from core.services import stock as stock_service


router = APIRouter(prefix="/api/webapp", tags=["webapp"])


# ============================================
# 🧰 HELPERS
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


def _decimal(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"))


# ============================================
# 🔐 AUTENTICAÇÃO TELEGRAM WEBAPP
# ============================================
def verify_telegram_init_data(init_data: str) -> Optional[dict]:
    """
    Valida o initData do Telegram WebApp.
    Retorna o dict do usuário ou None.

    Doc: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))

        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        # Monta a string de verificação
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        # Calcula o hash esperado
        secret_key = hmac.new(
            b"WebAppData",
            settings.telegram_bot_token.encode(),
            hashlib.sha256,
        ).digest()

        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, received_hash):
            logger.warning("🚫 Assinatura inválida do WebApp")
            return None

        # Verifica validade (até 24h)
        auth_date = int(parsed.get("auth_date", 0))
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if now_ts - auth_date > 86400:
            logger.warning("⏰ initData expirado")
            return None

        # Parseia o user
        user_json = parsed.get("user")
        if not user_json:
            return None

        user_data = json.loads(user_json)
        return user_data

    except Exception as e:
        logger.exception(f"❌ Erro ao validar initData: {e}")
        return None


async def get_current_user(
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependência que extrai o usuário logado do WebApp
    a partir do header X-Telegram-Init-Data.
    """
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="initData ausente")

    user_data = verify_telegram_init_data(x_telegram_init_data)
    if user_data is None:
        raise HTTPException(status_code=401, detail="initData inválido")

    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=401, detail="ID ausente")

    # Busca no banco
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        # Cria se não existir
        user = User(
            telegram_id=telegram_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            language_code=user_data.get("language_code"),
            status=UserStatus.ACTIVE,
            last_seen_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()

    if user.status == UserStatus.BLOCKED:
        raise HTTPException(status_code=403, detail="Usuário bloqueado")

    if user.status == UserStatus.BANNED:
        raise HTTPException(status_code=403, detail="Usuário banido")

    return user


# ============================================
# 📦 SCHEMAS
# ============================================
class CheckoutItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=100)


class CheckoutRequest(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1, max_length=50)


class RechargeRequest(BaseModel):
    amount: float = Field(gt=0)


# ============================================
# 🔐 AUTENTICAÇÃO (endpoint de teste)
# ============================================
@router.post("/auth")
async def webapp_auth(
    db: AsyncSession = Depends(get_db),
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
):
    """
    Valida o initData e retorna dados básicos.
    Útil pro frontend confirmar que está logado.
    """
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="initData ausente")

    user_data = verify_telegram_init_data(x_telegram_init_data)
    if user_data is None:
        raise HTTPException(status_code=401, detail="initData inválido")

    # Cria/busca o user
    telegram_id = user_data.get("id")
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            language_code=user_data.get("language_code"),
            status=UserStatus.ACTIVE,
            last_seen_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {
        "ok": True,
        "user": {
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "username": user.username,
            "balance": float(user.balance or 0),
            "points": user.points or 0,
            "affiliate_balance": float(user.affiliate_balance or 0),
        },
    }


# ============================================
# ⚙️ CONFIG (cores, textos, logo)
# ============================================
@router.get("/config")
async def webapp_config(db: AsyncSession = Depends(get_db)):
    """
    Retorna as configurações visuais do WebApp.
    Este endpoint NÃO requer autenticação
    (é só cor + título).
    """
    bot_name = await config_service.get_str(db, "bot_name", "Larizinha Store")
    site_title = await config_service.get_str(db, "site_title", bot_name)
    primary_color = await config_service.get_str(db, "site_primary_color", "#7c5cff")
    accent_color = await config_service.get_str(db, "site_accent_color", "#4f46e5")
    success_color = await config_service.get_str(db, "site_success_color", "#10b981")
    warning_color = await config_service.get_str(db, "site_warning_color", "#f59e0b")
    danger_color = await config_service.get_str(db, "site_danger_color", "#ef4444")
    banner_text = await config_service.get_str(db, "banner_text", "")
    logo_url = await config_service.get_str(db, "site_logo_url", "")
    support_link = await config_service.get_str(db, "support_link", "")
    pix_min = await config_service.get_decimal(db, "pix_min", "4.00")
    pix_max = await config_service.get_decimal(db, "pix_max", "500.00")
    bonus_percent = await config_service.get_decimal(db, "pix_bonus_percent", "0")
    bonus_min = await config_service.get_decimal(db, "pix_bonus_min", "0")
    cart_max = await config_service.get_int(db, "cart_max_items", 20)
    cart_max_qty = await config_service.get_int(db, "cart_max_quantity_per_item", 10)
    terms_text = await config_service.get_str(db, "terms_text", "")

    return {
        "bot_name": bot_name,
        "site_title": site_title,
        "colors": {
            "primary": primary_color,
            "accent": accent_color,
            "success": success_color,
            "warning": warning_color,
            "danger": danger_color,
        },
        "banner_text": banner_text,
        "logo_url": logo_url,
        "support_link": support_link,
        "cart": {
            "max_items": cart_max,
            "max_quantity_per_item": cart_max_qty,
        },
        "pix": {
            "min": float(pix_min),
            "max": float(pix_max),
            "bonus_percent": float(bonus_percent),
            "bonus_min": float(bonus_min),
        },
        "terms_text": terms_text[:500],
    }


# ============================================
# 👤 ME (dados do usuário logado)
# ============================================
@router.get("/me")
async def webapp_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna dados atualizados do usuário."""
    purchases = await db.scalar(
        select(func.count(Order.id)).where(
            Order.user_id == user.id,
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
        )
    ) or 0

    return {
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "username": user.username,
        "whatsapp": user.whatsapp,
        "email": user.email,
        "balance": float(user.balance or 0),
        "points": user.points or 0,
        "affiliate_balance": float(user.affiliate_balance or 0),
        "total_spent": float(user.total_spent or 0),
        "total_recharged": float(user.total_recharged or 0),
        "purchases_count": purchases,
    }


# ============================================
# 📱 CATÁLOGO
# ============================================
@router.get("/catalog")
async def webapp_catalog(db: AsyncSession = Depends(get_db)):
    """
    Retorna as categorias ativas + produtos com estoque.
    Não requer autenticação (o cliente vê antes de logar).
    """
    # Categorias
    cat_stmt = (
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.position, Category.name)
    )
    cat_result = await db.execute(cat_stmt)
    categories = list(cat_result.scalars().all())

    # Produtos ativos
    prod_stmt = (
        select(Product)
        .where(Product.status == ProductStatus.ACTIVE)
        .order_by(Product.position, Product.name)
    )
    prod_result = await db.execute(prod_stmt)
    products = list(prod_result.scalars().all())

    # Estoque por produto (uma query só)
    stock_stmt = (
        select(
            StockItem.product_id,
            func.count(StockItem.id).label("qty"),
        )
        .where(StockItem.status == StockStatus.AVAILABLE)
        .group_by(StockItem.product_id)
    )
    stock_result = await db.execute(stock_stmt)
    stock_map = {row.product_id: row.qty for row in stock_result.all()}

    # Monta resposta
    categories_out = [
        {
            "id": c.id,
            "name": c.name,
            "emoji": c.emoji or "📂",
            "description": c.description or "",
            "image_url": c.image_url or "",
        }
        for c in categories
    ]

    products_out = [
        {
            "id": p.id,
            "name": p.name,
            "emoji": p.emoji or "🎬",
            "description": p.description or "",
            "image_url": p.image_url or "",
            "price": float(p.price),
            "price_formatted": _format_brl(p.price),
            "category_id": p.category_id,
            "stock": stock_map.get(p.id, 0),
            "in_stock": stock_map.get(p.id, 0) > 0,
            "warranty_days": p.warranty_days,
            "duration_days": p.duration_days,
            "min_quantity": p.min_quantity,
            "max_quantity": p.max_quantity,
            "total_sold": p.total_sold or 0,
            "is_featured": p.is_featured,
        }
        for p in products
    ]

    return {
        "categories": categories_out,
        "products": products_out,
    }


# ============================================
# 📦 PRODUTO INDIVIDUAL
# ============================================
@router.get("/product/{product_id}")
async def webapp_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retorna detalhes de um produto."""
    product = await db.get(Product, product_id)
    if product is None or product.status != ProductStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    stock = await db.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product.id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    ) or 0

    return {
        "id": product.id,
        "name": product.name,
        "emoji": product.emoji or "🎬",
        "description": product.description or "",
        "image_url": product.image_url or "",
        "price": float(product.price),
        "price_formatted": _format_brl(product.price),
        "stock": stock,
        "in_stock": stock > 0,
        "warranty_days": product.warranty_days,
        "duration_days": product.duration_days,
        "min_quantity": product.min_quantity,
        "max_quantity": product.max_quantity,
        "total_sold": product.total_sold or 0,
        "category_id": product.category_id,
    }


# ============================================
# 🛒 CHECKOUT (finaliza compra)
# ============================================
@router.post("/checkout")
async def webapp_checkout(
    payload: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Finaliza a compra do carrinho.

    Fluxo:
      1. Valida cada item (produto existe, estoque, quantidade)
      2. Calcula total real (nunca confia no frontend)
      3. Verifica saldo
      4. Reserva estoque
      5. Cria pedido
      6. Debita saldo
      7. Marca como vendido
      8. Retorna sucesso + dados da compra
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="Carrinho vazio")

    # ─── 1. Valida cada item ───
    validated: list[dict[str, Any]] = []
    total_price = Decimal("0.00")

    for item in payload.items:
        product = await db.get(Product, item.product_id)
        if product is None or product.status != ProductStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail=f"Produto {item.product_id} indisponível",
            )

        if item.quantity < product.min_quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{product.name}: mínimo {product.min_quantity} unidade(s)"
                ),
            )

        if item.quantity > product.max_quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{product.name}: máximo {product.max_quantity} unidade(s)"
                ),
            )

        stock = await db.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == product.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0

        if stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{product.name}: apenas {stock} em estoque "
                    f"(pedido: {item.quantity})"
                ),
            )

        subtotal = _decimal(product.price) * item.quantity
        total_price += subtotal

        validated.append({
            "product": product,
            "quantity": item.quantity,
            "subtotal": subtotal,
        })

    total_price = _decimal(total_price)

    # ─── 2. Verifica saldo ───
    balance = _decimal(user.balance or Decimal("0.00"))

    if balance < total_price:
        missing = total_price - balance
        raise HTTPException(
            status_code=402,  # Payment Required
            detail={
                "error": "saldo_insuficiente",
                "balance": float(balance),
                "total": float(total_price),
                "missing": float(missing),
                "missing_formatted": _format_brl(missing),
            },
        )

    # ─── 3. Reserva + cria pedido + debita ───
    created_orders = []

    try:
        for v in validated:
            product = v["product"]
            quantity = v["quantity"]
            subtotal = v["subtotal"]

            # Reserva estoque
            items = await stock_service.reserve_items(
                session=db,
                product_id=product.id,
                quantity=quantity,
                user_telegram_id=user.telegram_id,
                reserve_minutes=15,
            )

            if len(items) < quantity:
                # Estorna o que já foi feito
                raise HTTPException(
                    status_code=400,
                    detail=f"Estoque insuficiente para {product.name}",
                )

            # Cria pedido
            order_code = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(days=product.duration_days)

            order = Order(
                order_code=order_code,
                user_id=user.id,
                user_telegram_id=user.telegram_id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.price,
                total_price=subtotal,
                status=OrderStatus.PAID,
                delivery_method="telegram",
                delivery_target=str(user.telegram_id),
                expires_at=expires_at,
            )
            db.add(order)
            await db.flush()

            # Marca itens como vendidos
            item_ids = [i.id for i in items]
            await stock_service.mark_as_sold(
                session=db,
                item_ids=item_ids,
                user_telegram_id=user.telegram_id,
                order_id=order.id,
                duration_days=product.duration_days,
            )

            # Debita
            user.balance = _decimal(user.balance) - subtotal
            user.total_spent = _decimal(user.total_spent) + subtotal
            user.purchases_count = (user.purchases_count or 0) + quantity
            db.add(user)

            # Total vendido
            product.total_sold = (product.total_sold or 0) + quantity
            db.add(product)

            created_orders.append({
                "order_code": order.order_code,
                "product_name": product.name,
                "quantity": quantity,
                "subtotal": float(subtotal),
                "items": [
                    {
                        "email": i.email,
                        "password": i.password,
                        "code": i.code,
                        "note": i.note,
                    }
                    for i in items
                ],
            })

        await db.commit()

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"❌ Erro no checkout: {e}")
        raise HTTPException(status_code=500, detail="Erro ao finalizar compra")

    # ─── 4. Entrega por Telegram em background ───
    try:
        from core.loader import bot
        from core.services import delivery as delivery_service

        for order_data in created_orders:
            stmt = select(Order).where(
                Order.order_code == order_data["order_code"]
            )
            result = await db.execute(stmt)
            order = result.scalar_one_or_none()

            if order is not None:
                await delivery_service.deliver_order(
                    session=db,
                    bot=bot,
                    order_id=order.id,
                )
    except Exception as e:
        logger.warning(f"⚠️ Falha ao entregar via Telegram: {e}")

    # ─── 5. Retorna sucesso ───
    await db.refresh(user)

    return {
        "success": True,
        "orders": created_orders,
        "total": float(total_price),
        "total_formatted": _format_brl(total_price),
        "new_balance": float(user.balance or 0),
        "new_balance_formatted": _format_brl(user.balance),
    }


# ============================================
# 💰 RECARGA (gera Pix)
# ============================================
@router.post("/recharge")
async def webapp_recharge(
    payload: RechargeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera um Pix de recarga."""
    try:
        amount = _decimal(payload.amount)
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Valor inválido")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Valor deve ser positivo")

    # Valida limites
    min_amount = await config_service.get_decimal(db, "pix_min", "4.00")
    max_amount = await config_service.get_decimal(db, "pix_max", "500.00")

    if amount < min_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Valor mínimo: R$ {_format_brl(min_amount)}",
        )

    if amount > max_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Valor máximo: R$ {_format_brl(max_amount)}",
        )

    # Cria Pix
    result = await payment_service.generate_recharge_pix(
        session=db,
        user=user,
        amount=amount,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Erro ao gerar Pix"),
        )

    await db.commit()

    payment = result["payment"]

    # Gera QR Code como base64
    qr_base64 = result.get("qr_code_base64", "")

    return {
        "success": True,
        "payment_id": payment.payment_id,
        "amount": float(amount),
        "amount_formatted": _format_brl(amount),
        "bonus": float(result.get("bonus_amount", 0)),
        "total_credited": float(result.get("total_credited", amount)),
        "pix_code": result.get("qr_code", ""),
        "qr_code_base64": qr_base64,
        "ticket_url": result.get("ticket_url", ""),
        "expires_at": payment.expires_at.isoformat() if payment.expires_at else None,
    }


# ============================================
# 🔄 STATUS DO PIX
# ============================================
@router.get("/payment/{payment_id}")
async def webapp_payment_status(
    payment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consulta status do Pix (roda verificação real no MP)."""
    # Confirma que o Pix é do usuário
    payment = await payment_service.get_payment_by_id(db, payment_id)
    if payment is None or payment.user_telegram_id != user.telegram_id:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    result = await payment_service.check_payment_status(
        session=db,
        payment_id=payment_id,
    )

    await db.commit()
    await db.refresh(user)

    return {
        "success": True,
        "status": result.get("status", "pending"),
        "balance": float(user.balance or 0),
        "balance_formatted": _format_brl(user.balance),
    }


# ============================================
# 📜 HISTÓRICO
# ============================================
@router.get("/history")
async def webapp_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Histórico de compras do usuário."""
    stmt = (
        select(Order)
        .where(
            Order.user_id == user.id,
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
        )
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    orders = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    orders_out = []

    for o in orders:
        is_active = bool(o.expires_at and o.expires_at > now)
        orders_out.append({
            "order_code": o.order_code,
            "product_name": o.product_name,
            "quantity": o.quantity,
            "total_price": float(o.total_price),
            "total_price_formatted": _format_brl(o.total_price),
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "expires_at": o.expires_at.isoformat() if o.expires_at else None,
            "is_active": is_active,
            "status": o.status.value,
        })

    return {
        "orders": orders_out,
        "total": len(orders_out),
    }


# ============================================
# 🛒 VALIDAR CARRINHO (sem comprar)
# ============================================
@router.post("/cart/validate")
async def webapp_validate_cart(
    payload: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Valida o carrinho SEM comprar.
    Retorna o que está OK, o que falta, etc.
    Útil pra o frontend mostrar antes de finalizar.
    """
    items_out = []
    total = Decimal("0.00")
    has_error = False

    for item in payload.items:
        product = await db.get(Product, item.product_id)
        if product is None or product.status != ProductStatus.ACTIVE:
            items_out.append({
                "product_id": item.product_id,
                "ok": False,
                "error": "Produto indisponível",
            })
            has_error = True
            continue

        stock = await db.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == product.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0

        qty = item.quantity
        ok = (
            qty >= product.min_quantity
            and qty <= product.max_quantity
            and qty <= stock
        )

        if not ok:
            has_error = True

        subtotal = _decimal(product.price) * qty
        if ok:
            total += subtotal

        items_out.append({
            "product_id": product.id,
            "name": product.name,
            "quantity": qty,
            "price": float(product.price),
            "subtotal": float(subtotal),
            "stock": stock,
            "ok": ok,
            "error": (
                None if ok
                else (
                    "Estoque insuficiente" if qty > stock
                    else "Quantidade fora do permitido"
                )
            ),
        })

    balance = _decimal(user.balance or Decimal("0.00"))
    missing = total - balance if total > balance else Decimal("0.00")

    return {
        "items": items_out,
        "total": float(total),
        "total_formatted": _format_brl(total),
        "balance": float(balance),
        "balance_formatted": _format_brl(balance),
        "enough_balance": balance >= total,
        "missing": float(missing),
        "missing_formatted": _format_brl(missing),
        "has_error": has_error,
        "can_checkout": not has_error and balance >= total,
    }
