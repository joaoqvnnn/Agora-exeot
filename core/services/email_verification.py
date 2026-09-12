# ============================================
# 📧 EMAIL VERIFICATION SERVICE — Larizinha Store
# ============================================
# Sistema PERSISTENTE de códigos de verificação.
#
# Antes: código em memória (perdia no restart)
# Agora: código no banco (sobrevive a restart)
#
# Funcionalidades:
#   - Criar código (com expiração + limite de tentativas)
#   - Enviar por e-mail (SMTP)
#   - Validar código
#   - Invalidar código (uso único)
#   - Bloqueio após exceder tentativas
#   - Rate limiting (evita spam de reenvio)
#   - Log de notificações (auditoria)
#   - Limpeza de códigos expirados
#   - Estatísticas
#
# Tipos de código:
#   - EMAIL_VERIFICATION: verificar e-mail de cadastro
#   - PASSWORD_RECOVERY: recuperar senha de saque
#   - PRODUCT_DELIVERY: entrega de produto
#   - EMAIL_CHANGE: trocar e-mail
#   - WITHDRAWAL_CONFIRM: confirmar saque
# ============================================

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    NotificationLog,
    User,
    VerificationCode,
    VerificationCodeType,
)
from core.services import config as config_service
from core.services import email as email_service


# ============================================
# ⚙️ CONFIGURAÇÕES PADRÃO
# ============================================
DEFAULT_EXPIRATION_MINUTES = 15      # tempo que o código dura
DEFAULT_MAX_ATTEMPTS = 5             # tentativas antes de bloquear
DEFAULT_RESEND_COOLDOWN_SECONDS = 60 # tempo mínimo entre reenvios
DEFAULT_LOCKOUT_MINUTES = 30         # tempo de bloqueio
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


# ============================================
# 📧 CRIAR + ENVIAR CÓDIGO
# ============================================
async def create_and_send_code(
    session: AsyncSession,
    email: str,
    code_type: VerificationCodeType,
    telegram_id: Optional[int] = None,
    extra_data: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Cria um código, salva no banco e envia por e-mail.

    Retorna:
      - success: bool
      - code_id: int
      - expires_at: datetime
      - expiration_minutes: int
      - max_attempts: int
      - error: str (se falhou)
    """
    email = email.strip().lower()

    # ─── 1. Validação básica ───
    if not EMAIL_REGEX.match(email):
        return {"success": False, "error": "E-mail inválido"}

    # ─── 2. Rate limit (evita spam de reenvio) ───
    cooldown_ok, remaining = await _check_resend_cooldown(
        session=session,
        email=email,
        code_type=code_type,
    )

    if not cooldown_ok:
        return {
            "success": False,
            "error": f"Aguarde {remaining}s para solicitar outro código",
            "cooldown_seconds": remaining,
        }

    # ─── 3. Invalida códigos antigos do mesmo tipo ───
    await _invalidate_previous_codes(
        session=session,
        email=email,
        code_type=code_type,
    )

    # ─── 4. Gera código ───
    code = _generate_code(6)

    expiration_minutes = await config_service.get_int(
        session,
        "verification_code_expiration_minutes",
        DEFAULT_EXPIRATION_MINUTES,
    )
    max_attempts = await config_service.get_int(
        session,
        "verification_code_max_attempts",
        DEFAULT_MAX_ATTEMPTS,
    )

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=expiration_minutes
    )

    # ─── 5. Cria registro no banco ───
    verification = VerificationCode(
        telegram_id=telegram_id,
        email=email,
        code=code,
        type=code_type,
        attempts=0,
        max_attempts=max_attempts,
        used=False,
        extra_data=extra_data or {},
        expires_at=expires_at,
    )
    session.add(verification)
    await session.flush()

    # ─── 6. Envia e-mail ───
    purpose_map = {
        VerificationCodeType.EMAIL_VERIFICATION: "Verificação de e-mail",
        VerificationCodeType.PASSWORD_RECOVERY: "Recuperação de senha",
        VerificationCodeType.PRODUCT_DELIVERY: "Entrega de produto",
        VerificationCodeType.EMAIL_CHANGE: "Troca de e-mail",
        VerificationCodeType.WITHDRAWAL_CONFIRM: "Confirmação de saque",
    }
    purpose = purpose_map.get(code_type, "Verificação")

    send_result = await email_service.send_verification_code(
        to_email=email,
        code=code,
        purpose=purpose,
    )

    # ─── 7. Registra log de notificação ───
    await _log_notification(
        session=session,
        channel="email",
        recipient=email,
        subject=f"Código de {purpose}",
        template="verification_code",
        status="sent" if send_result.get("success") else "failed",
        error_message=send_result.get("error"),
        telegram_id=telegram_id,
    )

    # ─── 8. Se falhou o envio ───
    if not send_result.get("success"):
        await session.rollback()
        return {
            "success": False,
            "error": send_result.get("error", "Erro ao enviar e-mail"),
        }

    logger.info(
        f"📧 Código enviado: {code_type.value} → {email} "
        f"(expira em {expiration_minutes}min)"
    )

    return {
        "success": True,
        "code_id": verification.id,
        "expires_at": expires_at,
        "expiration_minutes": expiration_minutes,
        "max_attempts": max_attempts,
    }


# ============================================
# ✅ VALIDAR CÓDIGO
# ============================================
async def validate_code(
    session: AsyncSession,
    email: str,
    code: str,
    code_type: VerificationCodeType,
) -> dict[str, Any]:
    """
    Valida um código digitado pelo usuário.

    Retorna:
      - success: bool
      - verification: VerificationCode (se sucesso)
      - error: str (se falhou)
      - attempts_remaining: int
      - locked: bool
      - expired: bool
    """
    email = email.strip().lower()
    code = code.strip()

    # ─── 1. Busca o código ativo mais recente ───
    stmt = (
        select(VerificationCode)
        .where(
            VerificationCode.email == email,
            VerificationCode.type == code_type,
            VerificationCode.used.is_(False),
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    verification = result.scalar_one_or_none()

    if verification is None:
        return {
            "success": False,
            "error": "Nenhum código ativo encontrado. Solicite um novo.",
        }

    # ─── 2. Já expirou? ───
    now = datetime.now(timezone.utc)
    if verification.expires_at < now:
        verification.used = True
        verification.used_at = now
        session.add(verification)
        await session.flush()
        return {
            "success": False,
            "error": "Código expirado. Solicite um novo.",
            "expired": True,
        }

    # ─── 3. Bloqueado por excesso de tentativas? ───
    if verification.attempts >= verification.max_attempts:
        lockout_minutes = await config_service.get_int(
            session,
            "verification_lockout_minutes",
            DEFAULT_LOCKOUT_MINUTES,
        )
        unlock_at = verification.created_at + timedelta(
            minutes=lockout_minutes
        )
        remaining = max(0, int((unlock_at - now).total_seconds() / 60))
        return {
            "success": False,
            "error": f"Muitas tentativas. Tente novamente em {remaining} minuto(s).",
            "locked": True,
        }

    # ─── 4. Código correto? (comparação em tempo constante) ───
    if not secrets.compare_digest(verification.code, code):
        verification.attempts += 1
        session.add(verification)
        await session.flush()

        remaining_attempts = verification.max_attempts - verification.attempts

        if remaining_attempts <= 0:
            return {
                "success": False,
                "error": "Código incorreto. Você excedeu o limite de tentativas.",
                "attempts_remaining": 0,
                "locked": True,
            }

        return {
            "success": False,
            "error": "Código incorreto",
            "attempts_remaining": remaining_attempts,
        }

    # ─── 5. Sucesso! Marca como usado ───
    verification.used = True
    verification.used_at = now
    session.add(verification)
    await session.flush()

    logger.info(f"✅ Código validado: {code_type.value} → {email}")

    return {
        "success": True,
        "verification": verification,
    }


# ============================================
# 🔄 REENVIAR CÓDIGO
# ============================================
async def resend_code(
    session: AsyncSession,
    email: str,
    code_type: VerificationCodeType,
    telegram_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Reenvia um código (respeita cooldown).
    """
    return await create_and_send_code(
        session=session,
        email=email,
        code_type=code_type,
        telegram_id=telegram_id,
    )


# ============================================
# 🧰 HELPERS INTERNOS
# ============================================
def _generate_code(length: int = 6) -> str:
    """Gera código numérico criptograficamente seguro."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


async def _check_resend_cooldown(
    session: AsyncSession,
    email: str,
    code_type: VerificationCodeType,
) -> tuple[bool, int]:
    """
    Verifica se pode reenviar (respeita cooldown).
    Retorna (pode_reenviar, segundos_restantes).
    """
    cooldown = await config_service.get_int(
        session,
        "verification_resend_cooldown_seconds",
        DEFAULT_RESEND_COOLDOWN_SECONDS,
    )

    if cooldown <= 0:
        return True, 0

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown)

    stmt = (
        select(VerificationCode)
        .where(
            VerificationCode.email == email,
            VerificationCode.type == code_type,
            VerificationCode.created_at > cutoff,
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    recent = result.scalar_one_or_none()

    if recent is None:
        return True, 0

    elapsed = (datetime.now(timezone.utc) - recent.created_at).total_seconds()
    remaining = int(cooldown - elapsed)

    if remaining > 0:
        return False, remaining

    return True, 0


async def _invalidate_previous_codes(
    session: AsyncSession,
    email: str,
    code_type: VerificationCodeType,
) -> int:
    """Invalida códigos ativos anteriores (mesmo tipo + email)."""
    stmt = select(VerificationCode).where(
        VerificationCode.email == email,
        VerificationCode.type == code_type,
        VerificationCode.used.is_(False),
    )
    result = await session.execute(stmt)
    codes = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    for code in codes:
        code.used = True
        code.used_at = now
        session.add(code)

    if codes:
        await session.flush()

    return len(codes)


async def _log_notification(
    session: AsyncSession,
    channel: str,
    recipient: str,
    subject: Optional[str] = None,
    template: Optional[str] = None,
    status: str = "sent",
    error_message: Optional[str] = None,
    telegram_id: Optional[int] = None,
) -> None:
    """Registra envio no log de notificações."""
    try:
        log = NotificationLog(
            channel=channel,
            recipient=recipient,
            subject=subject,
            template=template,
            status=status,
            error_message=error_message,
            telegram_id=telegram_id,
        )
        session.add(log)
        await session.flush()
    except Exception as e:
        logger.debug(f"⚠️ Falha ao registrar log de notificação: {e}")


# ============================================
# 🧹 LIMPAR CÓDIGOS EXPIRADOS (job)
# ============================================
async def clean_expired_codes(session: AsyncSession) -> int:
    """
    Remove códigos expirados ou já usados com mais de 24h.
    Chamado pelo job de limpeza diário.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    stmt = select(VerificationCode).where(
        (
            (VerificationCode.used.is_(True))
            | (VerificationCode.expires_at < cutoff)
        ),
        VerificationCode.created_at < cutoff,
    )
    result = await session.execute(stmt)
    codes = list(result.scalars().all())

    for code in codes:
        await session.delete(code)

    if codes:
        await session.flush()
        logger.info(f"🧹 {len(codes)} códigos expirados removidos")

    return len(codes)


# ============================================
# 📊 ESTATÍSTICAS
# ============================================
async def get_stats(session: AsyncSession, days: int = 30) -> dict[str, Any]:
    """Estatísticas de códigos enviados."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    total = await session.scalar(
        select(func.count(VerificationCode.id)).where(
            VerificationCode.created_at >= cutoff,
        )
    ) or 0

    by_type_stmt = (
        select(
            VerificationCode.type,
            func.count(VerificationCode.id).label("total"),
        )
        .where(VerificationCode.created_at >= cutoff)
        .group_by(VerificationCode.type)
    )
    by_type_result = await session.execute(by_type_stmt)
    by_type = {
        row.type.value: row.total
        for row in by_type_result.all()
    }

    used_count = await session.scalar(
        select(func.count(VerificationCode.id)).where(
            VerificationCode.created_at >= cutoff,
            VerificationCode.used.is_(True),
        )
    ) or 0

    return {
        "period_days": days,
        "total_codes": total,
        "used_codes": used_count,
        "by_type": by_type,
    }


# ============================================
# 📋 FLUXOS DE ALTO NÍVEL (wrappers)
# ============================================
async def send_email_verification(
    session: AsyncSession,
    user: User,
    new_email: str,
) -> dict[str, Any]:
    """Fluxo: verificar novo e-mail (troca de cadastro)."""
    return await create_and_send_code(
        session=session,
        email=new_email,
        code_type=VerificationCodeType.EMAIL_CHANGE,
        telegram_id=user.telegram_id,
        extra_data={"user_id": user.id},
    )


async def verify_email_change(
    session: AsyncSession,
    user: User,
    email: str,
    code: str,
) -> dict[str, Any]:
    """Valida código de troca de e-mail e atualiza o usuário."""
    result = await validate_code(
        session=session,
        email=email,
        code=code,
        code_type=VerificationCodeType.EMAIL_CHANGE,
    )

    if result.get("success"):
        user.email = email
        user.email_verified = True
        session.add(user)
        await session.flush()

        logger.info(
            f"✅ E-mail verificado: user={user.telegram_id} → {email}"
        )

    return result


async def send_password_recovery(
    session: AsyncSession,
    email: str,
    telegram_id: Optional[int] = None,
) -> dict[str, Any]:
    """Envia código de recuperação de senha."""
    return await create_and_send_code(
        session=session,
        email=email,
        code_type=VerificationCodeType.PASSWORD_RECOVERY,
        telegram_id=telegram_id,
    )


async def verify_password_recovery(
    session: AsyncSession,
    email: str,
    code: str,
) -> dict[str, Any]:
    """Valida código de recuperação (devolve verificação)."""
    return await validate_code(
        session=session,
        email=email,
        code=code,
        code_type=VerificationCodeType.PASSWORD_RECOVERY,
    )


async def send_product_delivery_code(
    session: AsyncSession,
    email: str,
    order_id: int,
    telegram_id: Optional[int] = None,
) -> dict[str, Any]:
    """Envia código pra confirmar entrega por e-mail."""
    return await create_and_send_code(
        session=session,
        email=email,
        code_type=VerificationCodeType.PRODUCT_DELIVERY,
        telegram_id=telegram_id,
        extra_data={"order_id": order_id},
    )


async def verify_product_delivery(
    session: AsyncSession,
    email: str,
    code: str,
) -> dict[str, Any]:
    """Valida código de entrega."""
    return await validate_code(
        session=session,
        email=email,
        code=code,
        code_type=VerificationCodeType.PRODUCT_DELIVERY,
    )


async def send_withdrawal_confirmation(
    session: AsyncSession,
    user: User,
    amount: float,
) -> dict[str, Any]:
    """Envia código pra confirmar saque."""
    if not user.email:
        return {"success": False, "error": "Usuário sem e-mail cadastrado"}

    return await create_and_send_code(
        session=session,
        email=user.email,
        code_type=VerificationCodeType.WITHDRAWAL_CONFIRM,
        telegram_id=user.telegram_id,
        extra_data={"amount": amount},
    )


async def verify_withdrawal_confirmation(
    session: AsyncSession,
    email: str,
    code: str,
) -> dict[str, Any]:
    """Valida código de confirmação de saque."""
    return await validate_code(
        session=session,
        email=email,
        code=code,
        code_type=VerificationCodeType.WITHDRAWAL_CONFIRM,
    )


# ============================================
# 🧪 TESTE (execução direta)
# ============================================
if __name__ == "__main__":
    import asyncio

    async def _test():
        from core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            print("🧪 Testando criação de código...")

            result = await create_and_send_code(
                session=session,
                email="teste@exemplo.com",
                code_type=VerificationCodeType.EMAIL_VERIFICATION,
            )

            print(f"Resultado: {result}")

    asyncio.run(_test())
