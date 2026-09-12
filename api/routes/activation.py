# ============================================
# 🔐 ACTIVATION ROUTES — Larizinha Store
# ============================================
# Backend da página de ativação.
#
# Fluxo:
#   1. Cliente compra produto por e-mail
#   2. Recebe e-mail com LINK DE ACESSO
#   3. Link contém token único (order_code + token)
#   4. Clica → página de ativação abre
#   5. Página pede apenas a SENHA DE SAQUE
#   6. Backend valida token + senha
#   7. Libera os dados do produto
#   8. Registra acesso na auditoria
#
# Segurança:
#   - Token expira em 30 dias (configurável)
#   - Limite de 5 tentativas de senha
#   - Bloqueio temporário após exceder
#   - Senha armazenada com bcrypt
#   - Sessão de ativação dura 24h
# ============================================

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from core.models import (
    Order,
    OrderStatus,
    StockItem,
    StockStatus,
    User,
)
from core.services import config as config_service


router = APIRouter(prefix="/api/activation", tags=["activation"])


# ============================================
# ⚙️ CONFIGURAÇÕES PADRÃO
# ============================================
DEFAULT_LINK_DAYS = 30
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_SESSION_HOURS = 24
DEFAULT_LOCKOUT_MINUTES = 30


# ============================================
# 🧠 CACHE EM MEMÓRIA DE TENTATIVAS
# ============================================
# {token_hash: {"attempts": int, "locked_until": datetime}}
_attempts_cache: dict[str, dict] = {}


def _token_hash(token: str) -> str:
    """Gera hash do token pra usar como chave de cache."""
    return hashlib.sha256(token.encode()).hexdigest()


# ============================================
# 📦 SCHEMAS
# ============================================
class ValidateTokenResponse(BaseModel):
    valid: bool
    order_code: str
    product_name: str
    quantity: int
    expires_at: Optional[str] = None
    link_expires_at: Optional[str] = None
    requires_password: bool = True
    already_activated: bool = False
    error: Optional[str] = None


class ActivateRequest(BaseModel):
    password: str = Field(min_length=4, max_length=32)


class StockItemOut(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    code: Optional[str] = None
    note: Optional[str] = None
    expires_at: Optional[str] = None


class ActivateResponse(BaseModel):
    success: bool
    product_name: Optional[str] = None
    order_code: Optional[str] = None
    quantity: Optional[int] = None
    items: list[StockItemOut] = []
    expires_at: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    attempts_remaining: Optional[int] = None


# ============================================
# 🧰 HELPERS
# ============================================
async def _get_config_int(
    db: AsyncSession, key: str, default: int
) -> int:
    return await config_service.get_int(db, key, default)


def _is_locked(token_hash: str) -> tuple[bool, int]:
    """
    Verifica se o token está bloqueado.
    Retorna (está_bloqueado, minutos_restantes).
    """
    entry = _attempts_cache.get(token_hash)
    if not entry:
        return False, 0

    locked_until = entry.get("locked_until")
    if not locked_until:
        return False, 0

    now = datetime.now(timezone.utc)
    if locked_until > now:
        remaining = int((locked_until - now).total_seconds() / 60) + 1
        return True, remaining

    # Lockout expirou — limpa
    _attempts_cache.pop(token_hash, None)
    return False, 0


def _register_failed_attempt(
    token_hash: str, max_attempts: int, lockout_minutes: int
) -> int:
    """
    Registra tentativa falha. Retorna tentativas restantes.
    Se exceder, bloqueia.
    """
    entry = _attempts_cache.get(token_hash) or {
        "attempts": 0,
        "locked_until": None,
    }

    entry["attempts"] = entry.get("attempts", 0) + 1

    if entry["attempts"] >= max_attempts:
        entry["locked_until"] = datetime.now(timezone.utc) + timedelta(
            minutes=lockout_minutes
        )
        _attempts_cache[token_hash] = entry
        return 0

    _attempts_cache[token_hash] = entry
    return max_attempts - entry["attempts"]


def _clear_attempts(token_hash: str) -> None:
    """Limpa cache de tentativas (senha correta)."""
    _attempts_cache.pop(token_hash, None)


def _find_order_code_from_token(token: str) -> Optional[str]:
    """
    Extrai o order_code do token.

    O token é formado por: {order_code}:{signature}
    Exemplo: 81c5465d-e71e-4b43-903a-e1dc567272ea:abc123...
    """
    if not token or ":" not in token:
        return None
    try:
        parts = token.split(":", 1)
        if len(parts) != 2 or len(parts[0]) < 10:
            return None
        return parts[0]
    except Exception:
        return None


def _verify_token_signature(order_code: str, token: str) -> bool:
    """
    Verifica a assinatura HMAC do token.
    Evita que alguém invente um token só com o order_code.
    """
    try:
        if ":" not in token:
            return False

        parts = token.split(":", 1)
        if len(parts) != 2:
            return False

        received_sig = parts[1]

        # Assinatura esperada = HMAC(secret, order_code)
        expected_sig = hashlib.sha256(
            f"{settings.secret_key}:{order_code}".encode()
        ).hexdigest()[:32]

        return secrets.compare_digest(received_sig, expected_sig)
    except Exception:
        return False


def generate_activation_token(order_code: str) -> str:
    """
    Gera o token de ativação pra um pedido.
    Usado pelo email_service quando envia o link.
    """
    signature = hashlib.sha256(
        f"{settings.secret_key}:{order_code}".encode()
    ).hexdigest()[:32]
    return f"{order_code}:{signature}"


# ============================================
# 🔍 VALIDAR TOKEN
# ============================================
@router.get("/validate/{token}")
async def validate_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> ValidateTokenResponse:
    """
    Valida o token de ativação vindo da URL.
    Chamado ANTES de mostrar o formulário de senha.
    """
    # Extrai order_code
    order_code = _find_order_code_from_token(token)
    if not order_code:
        return ValidateTokenResponse(
            valid=False,
            order_code="",
            product_name="",
            quantity=0,
            error="Link inválido ou corrompido",
        )

    # Verifica assinatura
    if not _verify_token_signature(order_code, token):
        logger.warning(f"🚫 Token com assinatura inválida: {order_code[:12]}...")
        return ValidateTokenResponse(
            valid=False,
            order_code="",
            product_name="",
            quantity=0,
            error="Link inválido",
        )

    # Busca o pedido
    stmt = select(Order).where(Order.order_code == order_code)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        return ValidateTokenResponse(
            valid=False,
            order_code="",
            product_name="",
            quantity=0,
            error="Pedido não encontrado",
        )

    # Verifica status
    if order.status not in (OrderStatus.PAID, OrderStatus.DELIVERED):
        return ValidateTokenResponse(
            valid=False,
            order_code=order.order_code,
            product_name=order.product_name,
            quantity=order.quantity,
            error="Pedido não está ativo",
        )

    # Verifica se o link expirou
    link_days = await _get_config_int(db, "activation_link_days", DEFAULT_LINK_DAYS)
    if link_days > 0 and order.delivered_at:
        link_expires = order.delivered_at + timedelta(days=link_days)
        if datetime.now(timezone.utc) > link_expires:
            return ValidateTokenResponse(
                valid=False,
                order_code=order.order_code,
                product_name=order.product_name,
                quantity=order.quantity,
                link_expires_at=link_expires.isoformat(),
                error=f"Este link expirou em {link_expires.strftime('%d/%m/%Y')}",
            )

    # Verifica se o token está bloqueado
    token_key = _token_hash(token)
    locked, remaining = _is_locked(token_key)
    if locked:
        return ValidateTokenResponse(
            valid=False,
            order_code=order.order_code,
            product_name=order.product_name,
            quantity=order.quantity,
            error=f"Muitas tentativas. Aguarde {remaining} minuto(s).",
        )

    # Calcula quando expira o link
    link_expires_at = None
    if link_days > 0 and order.delivered_at:
        link_expires_at = (
            order.delivered_at + timedelta(days=link_days)
        ).isoformat()

    # Retorna válido
    return ValidateTokenResponse(
        valid=True,
        order_code=order.order_code,
        product_name=order.product_name,
        quantity=order.quantity,
        expires_at=order.expires_at.isoformat() if order.expires_at else None,
        link_expires_at=link_expires_at,
        requires_password=True,
    )


# ============================================
# 🔓 ATIVAR PRODUTO (verifica senha)
# ============================================
@router.post("/activate/{token}")
async def activate_product(
    token: str,
    payload: ActivateRequest,
    db: AsyncSession = Depends(get_db),
) -> ActivateResponse:
    """
    Valida a senha do usuário e libera os dados do produto.
    """
    # Extrai order_code
    order_code = _find_order_code_from_token(token)
    if not order_code:
        return ActivateResponse(
            success=False,
            error="Link inválido",
        )

    # Verifica assinatura
    if not _verify_token_signature(order_code, token):
        return ActivateResponse(
            success=False,
            error="Link inválido",
        )

    # Verifica bloqueio
    token_key = _token_hash(token)
    locked, remaining = _is_locked(token_key)
    if locked:
        return ActivateResponse(
            success=False,
            error=f"Muitas tentativas. Aguarde {remaining} minuto(s).",
        )

    # Busca o pedido
    stmt = select(Order).where(Order.order_code == order_code)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        return ActivateResponse(
            success=False,
            error="Pedido não encontrado",
        )

    # Verifica status
    if order.status not in (OrderStatus.PAID, OrderStatus.DELIVERED):
        return ActivateResponse(
            success=False,
            error="Pedido não está ativo",
        )

    # Verifica expiração do link
    link_days = await _get_config_int(db, "activation_link_days", DEFAULT_LINK_DAYS)
    if link_days > 0 and order.delivered_at:
        link_expires = order.delivered_at + timedelta(days=link_days)
        if datetime.now(timezone.utc) > link_expires:
            return ActivateResponse(
                success=False,
                error=f"Este link expirou em {link_expires.strftime('%d/%m/%Y')}",
            )

    # Busca o usuário
    user = await db.get(User, order.user_id)
    if user is None:
        return ActivateResponse(
            success=False,
            error="Usuário não encontrado",
        )

    # Verifica se o usuário tem senha cadastrada
    if not user.withdrawal_password_hash:
        return ActivateResponse(
            success=False,
            error=(
                "Você ainda não cadastrou uma senha de saque. "
                "Cadastre pelo bot do Telegram antes de ativar."
            ),
        )

    # Verifica a senha
    password_ok = False
    try:
        from passlib.hash import bcrypt
        password_ok = bcrypt.verify(payload.password, user.withdrawal_password_hash)
    except Exception as e:
        logger.exception(f"❌ Erro ao verificar senha: {e}")
        return ActivateResponse(
            success=False,
            error="Erro ao verificar senha",
        )

    if not password_ok:
        # Registra tentativa falha
        max_attempts = await _get_config_int(
            db, "activation_max_attempts", DEFAULT_MAX_ATTEMPTS
        )
        lockout_minutes = await _get_config_int(
            db, "activation_lockout_minutes", DEFAULT_LOCKOUT_MINUTES
        )

        remaining_attempts = _register_failed_attempt(
            token_key, max_attempts, lockout_minutes
        )

        if remaining_attempts <= 0:
            logger.warning(f"🚫 Token bloqueado por excesso: {order_code[:12]}...")
            return ActivateResponse(
                success=False,
                error=f"Conta bloqueada por {lockout_minutes} minutos.",
                attempts_remaining=0,
            )

        return ActivateResponse(
            success=False,
            error="Senha incorreta",
            attempts_remaining=remaining_attempts,
        )

    # ✓ Senha correta
    _clear_attempts(token_key)

    # Busca os itens do pedido
    items_stmt = select(StockItem).where(StockItem.order_id == order.id)
    items_result = await db.execute(items_stmt)
    items = list(items_result.scalars().all())

    if not items:
        return ActivateResponse(
            success=False,
            error="Nenhum item encontrado para este pedido",
        )

    # Monta resposta
    items_out = []
    for item in items:
        items_out.append(
            StockItemOut(
                email=item.email,
                password=item.password,
                code=item.code,
                note=item.note,
                expires_at=item.expires_at.isoformat() if item.expires_at else None,
            )
        )

    # Registra acesso na auditoria
    try:
        from core.models import AuditLog
        log = AuditLog(
            admin_telegram_id=0,
            action="activation_success",
            target_type="order",
            target_id=order_code,
            new_value={
                "user_telegram_id": user.telegram_id,
                "ip": "web",
                "items_count": len(items),
            },
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        logger.debug(f"⚠️ Falha ao registrar auditoria: {e}")

    logger.info(
        f"✅ Ativação bem-sucedida: {order_code[:12]}... | "
        f"user={user.telegram_id}"
    )

    return ActivateResponse(
        success=True,
        product_name=order.product_name,
        order_code=order.order_code,
        quantity=order.quantity,
        items=items_out,
        expires_at=order.expires_at.isoformat() if order.expires_at else None,
        message="Produto liberado com sucesso!",
    )


# ============================================
# 🧪 TESTE (health)
# ============================================
@router.get("/health")
async def activation_health():
    """Verifica se o serviço está no ar."""
    return {
        "ok": True,
        "service": "activation",
        "version": "4.1.0",
        "attempts_cache_size": len(_attempts_cache),
    }


# ============================================
# 🧹 LIMPAR CACHE DE TENTATIVAS (job)
# ============================================
async def clean_attempts_cache() -> int:
    """
    Remove entradas antigas do cache de tentativas.
    Chamado pelo job de limpeza diário.
    """
    now = datetime.now(timezone.utc)
    keys_to_remove = []

    for key, entry in _attempts_cache.items():
        locked_until = entry.get("locked_until")
        if locked_until and locked_until < now - timedelta(hours=1):
            keys_to_remove.append(key)

    for key in keys_to_remove:
        _attempts_cache.pop(key, None)

    if keys_to_remove:
        logger.info(f"🧹 {len(keys_to_remove)} tokens de ativação limpos")

    return len(keys_to_remove)
