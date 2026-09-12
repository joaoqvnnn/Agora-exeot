# ============================================
# 📲 WHATSAPP FLOW — Larizinha Store
# ============================================
# Endpoint de ativação via WhatsApp.
#
# Como funciona (com Baileys):
#   1. Cliente compra escolhendo entrega por WhatsApp
#   2. Bot envia link no WhatsApp: /wa/activate/{token}
#   3. Cliente clica → abre o navegador do celular
#   4. Página web pede a senha de saque cadastrada
#   5. Backend valida senha
#   6. Produto é liberado na mesma página
#
# ⚠️ Diferença do "WhatsApp Flow" oficial:
#   - O Flow oficial do Meta não funciona com Baileys
#   - Aqui usamos um link web com token assinado (mesmo esquema do e-mail)
#   - Fluxo idêntico ao site de ativação, mas adaptado pro contexto do WhatsApp
#
# Reutiliza:
#   - generate_activation_token() do activation.py
#   - Validação de senha com bcrypt
#   - Cache de tentativas por token
# ============================================

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
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


router = APIRouter(prefix="/api/wa", tags=["whatsapp-flow"])


# ============================================
# ⚙️ CONFIGURAÇÕES
# ============================================
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCKOUT_MINUTES = 30
DEFAULT_LINK_DAYS = 30


# ============================================
# 🧠 CACHE DE TENTATIVAS
# ============================================
# {token_hash: {"attempts": int, "locked_until": datetime}}
_attempts_cache: dict[str, dict] = {}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _is_locked(token_hash: str) -> tuple[bool, int]:
    """Verifica se o token está bloqueado. Retorna (locked, mins_remaining)."""
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

    _attempts_cache.pop(token_hash, None)
    return False, 0


def _register_attempt(
    token_hash: str, max_attempts: int, lockout_minutes: int
) -> int:
    """Registra tentativa falha. Retorna tentativas restantes (0 se bloqueou)."""
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
    _attempts_cache.pop(token_hash, None)


# ============================================
# 🧰 HELPERS
# ============================================
def _find_order_code_from_token(token: str) -> Optional[str]:
    """Extrai o order_code do token."""
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
    """Verifica a assinatura HMAC do token."""
    try:
        if ":" not in token:
            return False

        parts = token.split(":", 1)
        if len(parts) != 2:
            return False

        received_sig = parts[1]
        expected_sig = hashlib.sha256(
            f"{settings.secret_key}:{order_code}".encode()
        ).hexdigest()[:32]

        return secrets.compare_digest(received_sig, expected_sig)
    except Exception:
        return False


def _format_date(dt) -> str:
    if not dt:
        return "N/A"
    try:
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return "N/A"


# ============================================
# 📦 SCHEMAS
# ============================================
class ValidateResponse(BaseModel):
    valid: bool
    order_code: str = ""
    product_name: str = ""
    quantity: int = 0
    expires_at: Optional[str] = None
    link_expires_at: Optional[str] = None
    error: Optional[str] = None


class ActivateRequest(BaseModel):
    password: str = Field(min_length=4, max_length=32)


class StockItemOut(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    code: Optional[str] = None
    note: Optional[str] = None


class ActivateResponse(BaseModel):
    success: bool
    product_name: Optional[str] = None
    order_code: Optional[str] = None
    quantity: Optional[int] = None
    items: list[StockItemOut] = []
    expires_at: Optional[str] = None
    error: Optional[str] = None
    attempts_remaining: Optional[int] = None


# ============================================
# 🔍 VALIDAR TOKEN
# ============================================
@router.get("/validate/{token}")
async def wa_validate_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> ValidateResponse:
    """
    Valida o token de ativação do WhatsApp.
    """
    # Extrai order_code
    order_code = _find_order_code_from_token(token)
    if not order_code:
        return ValidateResponse(valid=False, error="Link inválido")

    # Verifica assinatura
    if not _verify_token_signature(order_code, token):
        logger.warning(f"🚫 Token WA com assinatura inválida: {order_code[:12]}...")
        return ValidateResponse(valid=False, error="Link inválido")

    # Verifica bloqueio
    token_key = _token_hash(token)
    locked, remaining = _is_locked(token_key)
    if locked:
        return ValidateResponse(
            valid=False,
            error=f"Muitas tentativas. Aguarde {remaining} minuto(s).",
        )

    # Busca o pedido
    stmt = select(Order).where(Order.order_code == order_code)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        return ValidateResponse(valid=False, error="Pedido não encontrado")

    if order.status not in (OrderStatus.PAID, OrderStatus.DELIVERED):
        return ValidateResponse(
            valid=False,
            order_code=order.order_code,
            product_name=order.product_name,
            quantity=order.quantity,
            error="Pedido não está ativo",
        )

    # Verifica expiração do link
    link_days = await config_service.get_int(db, "activation_link_days", DEFAULT_LINK_DAYS)
    if link_days > 0 and order.delivered_at:
        link_expires = order.delivered_at + timedelta(days=link_days)
        if datetime.now(timezone.utc) > link_expires:
            return ValidateResponse(
                valid=False,
                order_code=order.order_code,
                product_name=order.product_name,
                quantity=order.quantity,
                link_expires_at=link_expires.isoformat(),
                error=f"Este link expirou em {link_expires.strftime('%d/%m/%Y')}",
            )

    link_expires_at = None
    if link_days > 0 and order.delivered_at:
        link_expires_at = (
            order.delivered_at + timedelta(days=link_days)
        ).isoformat()

    return ValidateResponse(
        valid=True,
        order_code=order.order_code,
        product_name=order.product_name,
        quantity=order.quantity,
        expires_at=order.expires_at.isoformat() if order.expires_at else None,
        link_expires_at=link_expires_at,
    )


# ============================================
# 🔓 ATIVAR (verifica senha)
# ============================================
@router.post("/activate/{token}")
async def wa_activate(
    token: str,
    payload: ActivateRequest,
    db: AsyncSession = Depends(get_db),
) -> ActivateResponse:
    """
    Valida a senha e libera o produto.
    """
    # Extrai order_code
    order_code = _find_order_code_from_token(token)
    if not order_code:
        return ActivateResponse(success=False, error="Link inválido")

    # Verifica assinatura
    if not _verify_token_signature(order_code, token):
        return ActivateResponse(success=False, error="Link inválido")

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
        return ActivateResponse(success=False, error="Pedido não encontrado")

    if order.status not in (OrderStatus.PAID, OrderStatus.DELIVERED):
        return ActivateResponse(success=False, error="Pedido não está ativo")

    # Verifica expiração do link
    link_days = await config_service.get_int(db, "activation_link_days", DEFAULT_LINK_DAYS)
    if link_days > 0 and order.delivered_at:
        link_expires = order.delivered_at + timedelta(days=link_days)
        if datetime.now(timezone.utc) > link_expires:
            return ActivateResponse(
                success=False,
                error=f"Link expirou em {link_expires.strftime('%d/%m/%Y')}",
            )

    # Busca usuário
    user = await db.get(User, order.user_id)
    if user is None:
        return ActivateResponse(success=False, error="Usuário não encontrado")

    if not user.withdrawal_password_hash:
        return ActivateResponse(
            success=False,
            error=(
                "Você ainda não cadastrou uma senha de saque. "
                "Cadastre pelo bot do Telegram antes de ativar."
            ),
        )

    # Verifica senha
    password_ok = False
    try:
        from passlib.hash import bcrypt
        password_ok = bcrypt.verify(payload.password, user.withdrawal_password_hash)
    except Exception as e:
        logger.exception(f"❌ Erro ao verificar senha: {e}")
        return ActivateResponse(success=False, error="Erro ao verificar senha")

    if not password_ok:
        max_attempts = await config_service.get_int(
            db, "activation_max_attempts", DEFAULT_MAX_ATTEMPTS
        )
        lockout_minutes = await config_service.get_int(
            db, "activation_lockout_minutes", DEFAULT_LOCKOUT_MINUTES
        )

        remaining_attempts = _register_attempt(
            token_key, max_attempts, lockout_minutes
        )

        if remaining_attempts <= 0:
            logger.warning(f"🚫 Token WA bloqueado: {order_code[:12]}...")
            return ActivateResponse(
                success=False,
                error=f"Bloqueado por {lockout_minutes} minutos.",
                attempts_remaining=0,
            )

        return ActivateResponse(
            success=False,
            error="Senha incorreta",
            attempts_remaining=remaining_attempts,
        )

    # ✓ Senha correta
    _clear_attempts(token_key)

    # Busca itens
    items_stmt = select(StockItem).where(StockItem.order_id == order.id)
    items_result = await db.execute(items_stmt)
    items = list(items_result.scalars().all())

    if not items:
        return ActivateResponse(
            success=False,
            error="Nenhum item encontrado para este pedido",
        )

    # Auditoria
    try:
        from core.models import AuditLog

        log = AuditLog(
            admin_telegram_id=0,
            action="wa_activation_success",
            target_type="order",
            target_id=order_code,
            new_value={
                "user_telegram_id": user.telegram_id,
                "channel": "whatsapp",
                "ip": "web",
                "items_count": len(items),
            },
        )
        db.add(log)
        await db.commit()
    except Exception:
        pass

    logger.info(
        f"✅ Ativação via WhatsApp: {order_code[:12]}... | "
        f"user={user.telegram_id}"
    )

    return ActivateResponse(
        success=True,
        product_name=order.product_name,
        order_code=order.order_code,
        quantity=order.quantity,
        items=[
            StockItemOut(
                email=item.email,
                password=item.password,
                code=item.code,
                note=item.note,
            )
            for item in items
        ],
        expires_at=order.expires_at.isoformat() if order.expires_at else None,
    )


# ============================================
# 🎨 PÁGINA DE ATIVAÇÃO (HTML)
# ============================================
@router.get("/activate/{token}", response_class=HTMLResponse)
async def wa_activate_page(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Renderiza a página HTML de ativação no navegador.
    """
    # Valida o token
    order_code = _find_order_code_from_token(token)
    if not order_code:
        return _render_error_page(
            "Link inválido",
            "O link que você acessou não está no formato esperado.",
        )

    if not _verify_token_signature(order_code, token):
        return _render_error_page(
            "Link inválido",
            "Este link não é válido.",
        )

    # Busca o pedido
    stmt = select(Order).where(Order.order_code == order_code)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        return _render_error_page(
            "Pedido não encontrado",
            "O pedido vinculado a este link não existe.",
        )

    if order.status not in (OrderStatus.PAID, OrderStatus.DELIVERED):
        return _render_error_page(
            "Pedido inativo",
            "Este pedido não está mais ativo.",
        )

    # Verifica expiração do link
    link_days = await config_service.get_int(db, "activation_link_days", DEFAULT_LINK_DAYS)
    if link_days > 0 and order.delivered_at:
        link_expires = order.delivered_at + timedelta(days=link_days)
        if datetime.now(timezone.utc) > link_expires:
            return _render_error_page(
                "Link expirado",
                f"Este link expirou em {link_expires.strftime('%d/%m/%Y')}.",
            )

    # Config visual
    bot_name = await config_service.get_str(db, "bot_name", "Larizinha Store")
    primary_color = await config_service.get_str(db, "site_primary_color", "#7c5cff")
    accent_color = await config_service.get_str(db, "site_accent_color", "#4f46e5")
    logo_url = await config_service.get_str(db, "site_logo_url", "")

    return HTMLResponse(
        content=_render_activate_page(
            token=token,
            product_name=order.product_name,
            order_code=order.order_code,
            quantity=order.quantity,
            expires_at=order.expires_at.strftime("%d/%m/%Y") if order.expires_at else "N/A",
            bot_name=bot_name,
            primary_color=primary_color,
            accent_color=accent_color,
            logo_url=logo_url,
        ),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ============================================
# 🔄 REENVIAR LINK
# ============================================
@router.post("/resend/{order_code}")
async def wa_resend_activation_link(
    order_code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Reenvia o link de ativação via WhatsApp.
    Útil quando o cliente perde o link.
    """
    stmt = select(Order).where(Order.order_code == order_code)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    user = await db.get(User, order.user_id)
    if user is None or not user.whatsapp:
        raise HTTPException(
            status_code=400,
            detail="Usuário não tem WhatsApp cadastrado",
        )

    # Gera novo token
    from api.routes.activation import generate_activation_token
    from core.services import wa_client

    token = generate_activation_token(order.order_code)
    activation_url = f"{settings.base_url.rstrip('/')}/api/wa/activate/{token}"

    message = (
        f"🔐 *Link de ativação - {order.product_name}*\n\n"
        f"🎫 Pedido: `{order.order_code[:16]}`\n\n"
        f"Clique no link abaixo pra acessar seu produto:\n\n"
        f"👉 {activation_url}\n\n"
        f"_Você precisará digitar sua senha de saque._"
    )

    result = await wa_client.send_message(user.whatsapp, message)

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Erro ao enviar"),
        )

    return {"ok": True, "message": "Link reenviado"}


# ============================================
# 🎨 TEMPLATES HTML
# ============================================
def _render_activate_page(
    token: str,
    product_name: str,
    order_code: str,
    quantity: int,
    expires_at: str,
    bot_name: str,
    primary_color: str,
    accent_color: str,
    logo_url: str,
) -> str:
    """
    Página HTML de ativação (mesmo design do activate.html principal,
    mas com toda a lógica inline).
    """
    logo_content = (
        f'<img src="{logo_url}" alt="Logo" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;">'
        if logo_url
        else "🔐"
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#0a0a0f">
    <meta name="robots" content="noindex, nofollow">
    <title>Ativar Produto · {bot_name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {{
            --color-primary: {primary_color};
            --color-accent: {accent_color};
            --color-primary-light: {primary_color}cc;
            --color-success: #10b981;
            --color-warning: #f59e0b;
            --color-danger: #ef4444;
            --bg-base: #0a0a0f;
            --bg-surface: #14141c;
            --bg-elevated: #1c1c28;
            --bg-overlay: #232334;
            --text-primary: #ffffff;
            --text-secondary: #b4b4c8;
            --text-muted: #6b6b80;
            --border-subtle: #2a2a3a;
            --border-strong: #3a3a4d;
            --radius-sm: 10px;
            --radius-md: 16px;
            --radius-lg: 22px;
            --radius-xl: 32px;
            --radius-full: 999px;
            --shadow-lg: 0 16px 48px rgba(0,0,0,0.5);
            --shadow-glow: 0 0 40px {primary_color}66;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
        html, body {{ height: 100%; overflow-x: hidden; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-base);
            color: var(--text-primary);
            font-size: 15px;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            position: relative;
        }}
        body::before {{
            content: '';
            position: fixed;
            inset: 0;
            background:
                radial-gradient(circle at 15% 5%, {primary_color}30, transparent 50%),
                radial-gradient(circle at 85% 95%, {accent_color}25, transparent 50%);
            pointer-events: none;
            z-index: 0;
        }}
        .container {{
            position: relative;
            z-index: 1;
            width: 100%;
            max-width: 480px;
            animation: fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .card {{
            background: linear-gradient(180deg, var(--bg-surface) 0%, var(--bg-elevated) 100%);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-xl);
            padding: 40px 28px;
            box-shadow: var(--shadow-lg);
            position: relative;
            overflow: hidden;
        }}
        .card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--color-primary), var(--color-accent), var(--color-primary));
            background-size: 200% 100%;
            animation: gradientSlide 4s linear infinite;
        }}
        @keyframes gradientSlide {{
            0% {{ background-position: 0% 0; }}
            100% {{ background-position: 200% 0; }}
        }}
        .logo {{
            width: 88px;
            height: 88px;
            border-radius: 26px;
            background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 42px;
            margin: 0 auto 24px;
            box-shadow: var(--shadow-glow);
            animation: logoFloat 3s ease-in-out infinite;
            color: white;
            overflow: hidden;
        }}
        @keyframes logoFloat {{
            0%, 100% {{ transform: translateY(0) scale(1); }}
            50% {{ transform: translateY(-6px) scale(1.02); }}
        }}
        h1 {{
            font-size: 24px;
            font-weight: 800;
            color: var(--text-primary);
            margin-bottom: 8px;
            letter-spacing: -0.03em;
            text-align: center;
            line-height: 1.25;
        }}
        .subtitle {{
            font-size: 14px;
            color: var(--text-muted);
            font-weight: 500;
            text-align: center;
            margin-bottom: 24px;
            line-height: 1.55;
        }}
        .info-box {{
            background: var(--bg-base);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 16px;
            margin-bottom: 24px;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            font-size: 13.5px;
            border-bottom: 1px solid var(--border-subtle);
        }}
        .info-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
        .info-row:first-child {{ padding-top: 0; }}
        .info-label {{ color: var(--text-muted); font-weight: 500; }}
        .info-value {{
            color: var(--text-primary);
            font-weight: 700;
            text-align: right;
            max-width: 60%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .info-value.success {{ color: var(--color-success); }}
        .alert {{
            padding: 14px 16px;
            border-radius: var(--radius-md);
            margin-bottom: 20px;
            font-size: 13.5px;
            line-height: 1.55;
            display: flex;
            gap: 12px;
            align-items: flex-start;
        }}
        .alert i {{ font-size: 16px; flex-shrink: 0; margin-top: 1px; }}
        .alert-content {{ flex: 1; }}
        .alert-content strong {{ display: block; margin-bottom: 2px; font-weight: 700; }}
        .alert.success {{ background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); color: var(--color-success); }}
        .alert.error {{ background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); color: var(--color-danger); }}
        .alert.warning {{ background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.25); color: var(--color-warning); }}
        .alert.info {{ background: {primary_color}15; border: 1px solid {primary_color}40; color: var(--color-primary-light); }}
        .password-box {{ position: relative; margin-bottom: 16px; }}
        .password-box label {{
            display: block;
            font-size: 13px;
            font-weight: 700;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .password-input-wrapper {{ position: relative; display: flex; align-items: center; }}
        .password-input-wrapper i.input-icon {{
            position: absolute;
            left: 16px;
            color: var(--text-muted);
            font-size: 15px;
            pointer-events: none;
        }}
        .password-input {{
            width: 100%;
            padding: 16px 48px 16px 46px;
            background: var(--bg-base);
            border: 2px solid var(--border-subtle);
            border-radius: var(--radius-md);
            color: var(--text-primary);
            font-size: 16px;
            font-weight: 600;
            letter-spacing: 0.15em;
            transition: all 0.25s ease;
            outline: none;
            font-family: inherit;
        }}
        .password-input::placeholder {{ letter-spacing: 0.05em; color: var(--text-muted); font-weight: 500; }}
        .password-input:focus {{
            border-color: var(--color-primary);
            box-shadow: 0 0 0 4px {primary_color}25;
            background: var(--bg-surface);
        }}
        .toggle-password {{
            position: absolute;
            right: 12px;
            width: 32px;
            height: 32px;
            border-radius: 10px;
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 14px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .toggle-password:active {{ background: var(--bg-overlay); color: var(--text-primary); transform: scale(0.9); }}
        .btn {{
            width: 100%;
            padding: 16px 24px;
            border-radius: var(--radius-md);
            font-size: 15px;
            font-weight: 700;
            font-family: inherit;
            cursor: pointer;
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            transition: all 0.25s ease;
            letter-spacing: -0.01em;
            position: relative;
            overflow: hidden;
        }}
        .btn:active:not(:disabled) {{ transform: scale(0.97); }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .btn-primary {{
            background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
            color: white;
            box-shadow: 0 8px 24px {primary_color}66;
        }}
        .btn.loading {{ pointer-events: none; }}
        .btn.loading::after {{
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            animation: shimmer 1.2s linear infinite;
        }}
        @keyframes shimmer {{
            0% {{ transform: translateX(-100%); }}
            100% {{ transform: translateX(100%); }}
        }}
        .spinner {{
            width: 18px;
            height: 18px;
            border-radius: 50%;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: white;
            animation: spin 0.7s linear infinite;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .attempts {{
            text-align: center;
            font-size: 12.5px;
            color: var(--text-muted);
            margin-top: 14px;
            font-weight: 600;
        }}
        .attempts strong {{ color: var(--color-warning); }}
        .products-container {{ display: flex; flex-direction: column; gap: 14px; margin-top: 20px; }}
        .product-item {{
            background: var(--bg-base);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 18px;
            animation: productPop 0.5s cubic-bezier(0.16, 1, 0.3, 1) backwards;
            position: relative;
        }}
        .product-item::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, var(--color-success), transparent);
        }}
        @keyframes productPop {{
            from {{ opacity: 0; transform: scale(0.95) translateY(10px); }}
            to {{ opacity: 1; transform: scale(1) translateY(0); }}
        }}
        .product-item-title {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            font-weight: 800;
            color: var(--color-success);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 14px;
        }}
        .product-field {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 10px 0;
            border-bottom: 1px dashed var(--border-subtle);
            font-size: 13.5px;
        }}
        .product-field:last-child {{ border-bottom: none; padding-bottom: 0; }}
        .product-field-icon {{
            width: 24px;
            height: 24px;
            border-radius: 8px;
            background: {primary_color}20;
            color: var(--color-primary-light);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            flex-shrink: 0;
            margin-top: 1px;
        }}
        .product-field-content {{ flex: 1; min-width: 0; }}
        .product-field-label {{
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 3px;
        }}
        .product-field-value {{
            color: var(--text-primary);
            font-weight: 700;
            font-size: 14px;
            word-break: break-all;
            line-height: 1.4;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }}
        .product-field-value code {{
            font-family: 'Courier New', monospace;
            background: var(--bg-surface);
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 13px;
            flex: 1;
            word-break: break-all;
        }}
        .copy-btn {{
            width: 30px;
            height: 30px;
            border-radius: 8px;
            background: {primary_color}20;
            border: 1px solid {primary_color}40;
            color: var(--color-primary-light);
            font-size: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .copy-btn:active {{ background: var(--color-primary); color: white; transform: scale(0.9); }}
        .copy-btn.copied {{ background: var(--color-success); color: white; border-color: var(--color-success); }}
        .footer {{
            text-align: center;
            margin-top: 24px;
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.6;
        }}
        .toast-container {{
            position: fixed;
            top: 20px;
            left: 16px;
            right: 16px;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            gap: 10px;
            pointer-events: none;
        }}
        .toast {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 14px 16px;
            background: rgba(28,28,40,0.95);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-lg);
            color: var(--text-primary);
            font-size: 13.5px;
            font-weight: 600;
            animation: toastSlide 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            pointer-events: auto;
        }}
        @keyframes toastSlide {{
            from {{ opacity: 0; transform: translateY(-20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .toast-icon {{
            width: 30px;
            height: 30px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            flex-shrink: 0;
        }}
        .toast.success .toast-icon {{ background: rgba(16,185,129,0.15); color: var(--color-success); }}
        .toast.error .toast-icon {{ background: rgba(239,68,68,0.15); color: var(--color-danger); }}
        .toast.info .toast-icon {{ background: {primary_color}20; color: var(--color-primary-light); }}
        .hidden {{ display: none !important; }}
        @keyframes shake {{
            0%, 100% {{ transform: translateX(0); }}
            20% {{ transform: translateX(-8px); }}
            40% {{ transform: translateX(8px); }}
            60% {{ transform: translateX(-5px); }}
            80% {{ transform: translateX(5px); }}
        }}
        @media (max-width: 400px) {{
            .card {{ padding: 32px 20px; border-radius: 24px; }}
            h1 {{ font-size: 21px; }}
            .logo {{ width: 76px; height: 76px; font-size: 36px; }}
        }}
    </style>
</head>
<body>
    <div class="toast-container" id="toast-container"></div>

    <div class="container">
        <div class="card" id="card">

            <!-- Loading -->
            <div id="state-loading">
                <div class="logo">{logo_content}</div>
                <h1>Verificando link...</h1>
                <p class="subtitle">Aguarde um instante</p>
            </div>

            <!-- Invalid -->
            <div id="state-invalid" class="hidden">
                <div class="logo" style="background: linear-gradient(135deg, #ef4444, #dc2626);">⚠️</div>
                <h1>Link inválido</h1>
                <p class="subtitle" id="invalid-message">Este link não é válido ou expirou.</p>
                <div class="alert info">
                    <i class="fa-solid fa-circle-info"></i>
                    <div class="alert-content">
                        <strong>Precisa de ajuda?</strong>
                        Volte ao WhatsApp e peça um novo link ou fale com o suporte.
                    </div>
                </div>
            </div>

            <!-- Password -->
            <div id="state-password" class="hidden">
                <div class="logo">{logo_content}</div>
                <h1>Ativar produto</h1>
                <p class="subtitle">Digite sua senha de saque pra liberar.</p>

                <div class="info-box">
                    <div class="info-row">
                        <span class="info-label">Produto</span>
                        <span class="info-value" id="info-product">—</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Pedido</span>
                        <span class="info-value" id="info-order">—</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Quantidade</span>
                        <span class="info-value" id="info-quantity">—</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Vence em</span>
                        <span class="info-value" id="info-expires">—</span>
                    </div>
                </div>

                <form id="password-form" autocomplete="off">
                    <div class="password-box">
                        <label for="password">Sua senha</label>
                        <div class="password-input-wrapper">
                            <i class="fa-solid fa-lock input-icon"></i>
                            <input
                                type="password"
                                id="password"
                                class="password-input"
                                placeholder="••••"
                                inputmode="numeric"
                                pattern="[0-9]*"
                                maxlength="32"
                                autocomplete="off"
                                required
                            >
                            <button type="button" class="toggle-password" id="toggle-password">
                                <i class="fa-solid fa-eye"></i>
                            </button>
                        </div>
                    </div>

                    <button type="submit" class="btn btn-primary" id="submit-btn">
                        <i class="fa-solid fa-lock-open"></i>
                        <span>Ativar produto</span>
                    </button>
                </form>

                <div class="attempts hidden" id="attempts-info">
                    Tentativas restantes: <strong id="attempts-count">5</strong>
                </div>

                <div class="alert warning" style="margin-top:20px;">
                    <i class="fa-solid fa-shield-halved"></i>
                    <div class="alert-content">
                        <strong>Por que pedir senha?</strong>
                        Sua senha protege os dados. É a mesma que você cadastrou no bot.
                    </div>
                </div>
            </div>

            <!-- Success -->
            <div id="state-success" class="hidden">
                <div class="logo" style="background: linear-gradient(135deg, #10b981, #059669);">✓</div>
                <h1>Produto liberado!</h1>
                <p class="subtitle" id="success-subtitle">Aqui estão seus dados. Guarde em local seguro.</p>

                <div class="info-box">
                    <div class="info-row">
                        <span class="info-label">Produto</span>
                        <span class="info-value success" id="success-product">—</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Quantidade</span>
                        <span class="info-value" id="success-quantity">—</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Vence em</span>
                        <span class="info-value" id="success-expires">—</span>
                    </div>
                </div>

                <div class="alert success">
                    <i class="fa-solid fa-circle-check"></i>
                    <div class="alert-content">
                        <strong>Pronto pra usar!</strong>
                        Copie os dados e use conforme descrito.
                    </div>
                </div>

                <div class="products-container" id="products-container"></div>

                <div class="alert warning" style="margin-top:20px;">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <div class="alert-content">
                        <strong>Importante</strong>
                        Não compartilhe. Cada login é único e monitorado.
                    </div>
                </div>
            </div>

        </div>

        <div class="footer">
            🔐 Ambiente seguro · {bot_name}
        </div>
    </div>

<script>
(function() {{
    'use strict';

    const TOKEN = {repr(token)};
    const State = {{
        productName: {repr(product_name)},
        orderCode: {repr(order_code)},
        quantity: {quantity},
        expiresAt: {repr(expires_at)},
    }};

    function $(id) {{ return document.getElementById(id); }}

    function escapeHtml(str) {{
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = String(str);
        return d.innerHTML;
    }}

    function toast(msg, type) {{
        type = type || 'info';
        const c = $('toast-container');
        const icons = {{ success: 'fa-check', error: 'fa-xmark', warning: 'fa-triangle-exclamation', info: 'fa-circle-info' }};
        const el = document.createElement('div');
        el.className = 'toast ' + type;
        el.innerHTML = '<div class="toast-icon"><i class="fa-solid ' + (icons[type] || icons.info) + '"></i></div><div>' + escapeHtml(msg) + '</div>';
        c.appendChild(el);
        setTimeout(() => el.remove(), 3200);
    }}

    function showState(name) {{
        ['loading', 'invalid', 'password', 'success'].forEach(s => {{
            const el = $('state-' + s);
            if (el) {{
                if (s === name) el.classList.remove('hidden');
                else el.classList.add('hidden');
            }}
        }});
    }}

    async function validateToken() {{
        const res = await fetch('/api/wa/validate/' + encodeURIComponent(TOKEN));
        return res.json();
    }}

    async function activate(password) {{
        const res = await fetch('/api/wa/activate/' + encodeURIComponent(TOKEN), {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ password }}),
        }});
        return res.json();
    }}

    async function init() {{
        try {{
            const result = await validateToken();

            if (!result.valid) {{
                $('invalid-message').textContent = result.error || 'Link inválido';
                showState('invalid');
                return;
            }}

            $('info-product').textContent = result.product_name || '—';
            $('info-order').textContent = (result.order_code || '').slice(0, 16) + '...';
            $('info-quantity').textContent = result.quantity || 1;
            $('info-expires').textContent = State.expiresAt;

            showState('password');
            setTimeout(() => $('password').focus(), 300);

        }} catch (e) {{
            $('invalid-message').textContent = 'Erro ao verificar link';
            showState('invalid');
        }}
    }}

    function renderField(label, value, icon) {{
        const safe = escapeHtml(value);
        return '<div class="product-field"><div class="product-field-icon"><i class="fa-solid ' + icon + '"></i></div><div class="product-field-content"><div class="product-field-label">' + label + '</div><div class="product-field-value"><code>' + safe + '</code><button class="copy-btn" data-value="' + safe + '"><i class="fa-solid fa-copy"></i></button></div></div></div>';
    }}

    function showSuccess(result) {{
        showState('success');
        $('success-product').textContent = result.product_name || '—';
        $('success-quantity').textContent = result.quantity || 1;
        $('success-expires').textContent = State.expiresAt;

        const items = result.items || [];
        $('success-subtitle').textContent = items.length > 1
            ? 'Aqui estão seus ' + items.length + ' logins.'
            : 'Aqui está seu login.';

        const container = $('products-container');
        container.innerHTML = '';

        items.forEach((item, i) => {{
            let html = '<div class="product-item-title"><i class="fa-solid fa-check-circle"></i>' + (items.length > 1 ? 'Login ' + (i + 1) + ' de ' + items.length : 'Seus dados') + '</div>';
            if (item.email) html += renderField('Email', item.email, 'fa-envelope');
            if (item.password) html += renderField('Senha', item.password, 'fa-key');
            if (item.code) html += renderField('Código', item.code, 'fa-link');
            if (item.note) html += '<div class="product-field"><div class="product-field-icon"><i class="fa-solid fa-note-sticky"></i></div><div class="product-field-content"><div class="product-field-label">Nota</div><div class="product-field-value" style="font-size:13px;font-weight:500;color:var(--text-secondary);">' + escapeHtml(item.note) + '</div></div></div>';

            const el = document.createElement('div');
            el.className = 'product-item';
            el.innerHTML = html;
            container.appendChild(el);
        }});

        container.querySelectorAll('.copy-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                const v = btn.getAttribute('data-value') || '';
                if (navigator.clipboard) {{
                    navigator.clipboard.writeText(v).then(() => {{
                        btn.classList.add('copied');
                        btn.innerHTML = '<i class="fa-solid fa-check"></i>';
                        toast('Copiado!', 'success');
                        setTimeout(() => {{
                            btn.classList.remove('copied');
                            btn.innerHTML = '<i class="fa-solid fa-copy"></i>';
                        }}, 2000);
                    }});
                }}
            }});
        }});

        toast('Produto liberado!', 'success');
    }}

    $('password-form').addEventListener('submit', async (e) => {{
        e.preventDefault();
        const input = $('password');
        const btn = $('submit-btn');
        const pwd = (input.value || '').trim();

        if (pwd.length < 4) {{
            toast('Senha muito curta', 'error');
            return;
        }}

        btn.disabled = true;
        btn.innerHTML = '<div class="spinner"></div><span>Verificando...</span>';

        try {{
            const result = await activate(pwd);

            if (!result.success) {{
                if (result.attempts_remaining !== undefined && result.attempts_remaining !== null) {{
                    $('attempts-info').classList.remove('hidden');
                    $('attempts-count').textContent = result.attempts_remaining;
                }}

                toast(result.error || 'Senha incorreta', 'error');

                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-lock-open"></i><span>Ativar produto</span>';

                input.style.animation = 'none';
                setTimeout(() => {{ input.style.animation = 'shake 0.4s'; }}, 10);
                return;
            }}

            showSuccess(result);

        }} catch (err) {{
            toast('Erro ao ativar', 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-lock-open"></i><span>Ativar produto</span>';
        }}
    }});

    $('toggle-password').addEventListener('click', () => {{
        const input = $('password');
        const t = $('toggle-password');
        const isPwd = input.type === 'password';
        input.type = isPwd ? 'text' : 'password';
        t.innerHTML = isPwd ? '<i class="fa-solid fa-eye-slash"></i>' : '<i class="fa-solid fa-eye"></i>';
    }});

    init();
}})();
</script>
</body>
</html>"""


def _render_error_page(title: str, message: str) -> str:
    """Renderiza uma página de erro genérica."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>{title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: #0a0a0f;
            color: #fff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: linear-gradient(180deg, #14141c 0%, #1c1c28 100%);
            border: 1px solid #2a2a3a;
            border-radius: 32px;
            padding: 40px 28px;
            max-width: 420px;
            width: 100%;
            text-align: center;
            box-shadow: 0 16px 48px rgba(0,0,0,0.5);
        }}
        .icon {{
            width: 88px;
            height: 88px;
            border-radius: 26px;
            background: linear-gradient(135deg, #ef4444, #dc2626);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 42px;
            margin: 0 auto 24px;
            box-shadow: 0 0 40px rgba(239,68,68,0.4);
            color: white;
        }}
        h1 {{ font-size: 22px; font-weight: 800; margin-bottom: 12px; }}
        p {{ color: #b4b4c8; font-size: 14px; line-height: 1.6; }}
        .footer {{
            margin-top: 24px;
            font-size: 12px;
            color: #6b6b80;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon"><i class="fa-solid fa-triangle-exclamation"></i></div>
        <h1>{title}</h1>
        <p>{message}</p>
        <p class="footer">Se precisar de ajuda, entre em contato pelo WhatsApp.</p>
    </div>
</body>
</html>"""


# ============================================
# 🏥 HEALTHCHECK
# ============================================
@router.get("/health")
async def wa_flow_health():
    """Healthcheck do WhatsApp Flow."""
    return {
        "ok": True,
        "service": "whatsapp-flow",
        "version": "4.1.0",
        "cached_attempts": len(_attempts_cache),
    }
