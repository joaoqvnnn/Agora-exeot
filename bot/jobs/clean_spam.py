# ============================================
# 🧹 CLEAN SPAM — Larizinha Store
# ============================================
# Job que limpa o cache anti-spam do WhatsApp.
#
# O cache do wa_handler guarda:
#   {phone: {"last_msg": str, "count": int,
#            "first_at": datetime, "blocked_until": datetime}}
#
# Entradas antigas (mais de 1h) sem bloqueio ativo
# são removidas pra liberar memória.
#
# Também limpa cache de tentativas dos links
# de ativação do WhatsApp (whatsapp_flow.py).
#
# Roda a cada 30 minutos via APScheduler.
# ============================================

from loguru import logger

from core.database import AsyncSessionLocal


async def job_clean_spam() -> None:
    """
    Limpa caches em memória de:
      - Anti-spam do WhatsApp (wa_handler)
      - Tentativas de ativação (whatsapp_flow)
      - Tentativas de ativação (activation)
    """
    try:
        total_removed = 0

        # ─── 1. Cache anti-spam do WhatsApp ───
        try:
            from core.services.wa_handler import clean_spam_cache

            count = await clean_spam_cache()
            if count:
                logger.info(f"🧹 WhatsApp spam cache: {count} entradas removidas")
                total_removed += count
        except Exception as e:
            logger.debug(f"⚠️ Falha ao limpar spam cache: {e}")

        # ─── 2. Cache de tentativas do WhatsApp Flow ───
        try:
            from api.routes.whatsapp_flow import _attempts_cache as wa_flow_cache
            from datetime import datetime, timedelta, timezone

            removed_wa = _clean_attempts_cache(
                wa_flow_cache,
                lockout_buffer_minutes=60,
            )
            if removed_wa:
                logger.info(f"🧹 WA Flow attempts: {removed_wa} entradas removidas")
                total_removed += removed_wa
        except Exception as e:
            logger.debug(f"⚠️ Falha ao limpar WA flow cache: {e}")

        # ─── 3. Cache de tentativas do e-mail activation ───
        try:
            from api.routes.activation import _attempts_cache as email_cache

            removed_email = _clean_attempts_cache(
                email_cache,
                lockout_buffer_minutes=60,
            )
            if removed_email:
                logger.info(f"🧹 Email attempts: {removed_email} entradas removidas")
                total_removed += removed_email
        except Exception as e:
            logger.debug(f"⚠️ Falha ao limpar email cache: {e}")

        # ─── 4. Limpa códigos de verificação expirados no banco ───
        try:
            from core.services import email_verification

            async with AsyncSessionLocal() as session:
                codes_count = await email_verification.clean_expired_codes(session)
                if codes_count:
                    await session.commit()
                    logger.info(f"🧹 Verification codes: {codes_count} removidos")
                    total_removed += codes_count
        except Exception as e:
            logger.debug(f"⚠️ Falha ao limpar verification codes: {e}")

        # ─── Log final ───
        if total_removed > 0:
            logger.info(f"🧹 Total limpo: {total_removed} entrada(s)")
        else:
            logger.debug("🧹 Nada pra limpar")

    except Exception as e:
        logger.exception(f"❌ Erro no job clean_spam: {e}")


def _clean_attempts_cache(
    cache: dict,
    lockout_buffer_minutes: int = 60,
) -> int:
    """
    Remove entradas antigas de um cache de tentativas.

    Uma entrada é removida se:
      - Não tem bloqueio ativo E
      - O primeiro acesso foi há mais de `lockout_buffer_minutes`

    Args:
        cache: dict {token_hash: {"attempts": int, "locked_until": datetime}}
        lockout_buffer_minutes: minutos de tolerância após bloqueio expirar

    Returns:
        Quantidade de entradas removidas
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=lockout_buffer_minutes)

    keys_to_remove = []

    for key, entry in cache.items():
        locked_until = entry.get("locked_until")

        # Se tem bloqueio ativo → mantém
        if locked_until and locked_until > now:
            continue

        # Se o bloqueio expirou há mais de 1h → pode remover
        if locked_until and locked_until < cutoff:
            keys_to_remove.append(key)
            continue

        # Se não tem bloqueio e o entry é muito antigo
        # (assume que o entry tem "first_at" ou é antigo)
        first_at = entry.get("first_at")
        if first_at and first_at < cutoff:
            keys_to_remove.append(key)
            continue

        # Fallback: se não tem timestamps e não tem bloqueio,
        # considera órfão e remove (entrada muito antiga)
        if not locked_until and not first_at:
            # Só remove se a entrada tem mais de 100 tentativas
            # (evita remover entradas em uso)
            if entry.get("attempts", 0) == 0:
                keys_to_remove.append(key)

    for key in keys_to_remove:
        cache.pop(key, None)

    return len(keys_to_remove)


# ============================================
# 📊 ESTATÍSTICAS DO CACHE
# ============================================
async def get_cache_stats() -> dict:
    """
    Retorna estatísticas dos caches em memória.
    Útil pra painel admin / diagnóstico.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    stats = {
        "wa_spam_cache": 0,
        "wa_flow_cache": 0,
        "email_activation_cache": 0,
        "total_locked": 0,
    }

    # WhatsApp spam cache
    try:
        from core.services.wa_handler import _spam_cache

        stats["wa_spam_cache"] = len(_spam_cache)

        for entry in _spam_cache.values():
            blocked_until = entry.get("blocked_until")
            if blocked_until and blocked_until > now:
                stats["total_locked"] += 1
    except Exception:
        pass

    # WhatsApp Flow attempts
    try:
        from api.routes.whatsapp_flow import _attempts_cache as wa_flow_cache

        stats["wa_flow_cache"] = len(wa_flow_cache)

        for entry in wa_flow_cache.values():
            locked_until = entry.get("locked_until")
            if locked_until and locked_until > now:
                stats["total_locked"] += 1
    except Exception:
        pass

    # Email activation attempts
    try:
        from api.routes.activation import _attempts_cache as email_cache

        stats["email_activation_cache"] = len(email_cache)

        for entry in email_cache.values():
            locked_until = entry.get("locked_until")
            if locked_until and locked_until > now:
                stats["total_locked"] += 1
    except Exception:
        pass

    return stats
