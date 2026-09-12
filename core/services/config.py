# ============================================
# ⚙️ CONFIG SERVICE — Larizinha Store
# ============================================
# Lê e grava configurações da tabela "configs".
# Todo o painel admin usa este serviço.
# Suporta cache em memória pra evitar consultas repetidas.
# ============================================

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Config


# ============================================
# 📚 DEFAULTS — Configurações padrão
# ============================================
# Se a chave não existir no banco, é criada com este valor.
# ============================================
DEFAULTS: dict[str, dict[str, Any]] = {
    # Gerais
    "bot_name": {"value": "Larizinha Store", "type": "string", "category": "geral",
                 "description": "Nome do bot exibido nas mensagens"},
    "support_link": {"value": "https://wa.me/5511999999999", "type": "string",
                     "category": "geral", "description": "Link de suporte"},
    "logs_channel_id": {"value": "", "type": "string", "category": "geral",
                        "description": "ID do canal de logs"},
    "separator": {"value": "===", "type": "string", "category": "geral",
                  "description": "Separador usado nos comandos do admin"},

    # Manutenção
    "maintenance_mode": {"value": "false", "type": "bool", "category": "manutencao",
                         "description": "Bot em manutenção?"},
    "maintenance_message": {"value": "", "type": "string", "category": "manutencao",
                            "description": "Mensagem durante manutenção"},
    "maintenance_return_message": {"value": "", "type": "string",
                                   "category": "manutencao",
                                   "description": "Mensagem ao voltar"},

    # Canal obrigatório
    "required_channel_enabled": {"value": "false", "type": "bool",
                                 "category": "canal",
                                 "description": "Exigir entrada no canal?"},
    "required_channel_id": {"value": "", "type": "string", "category": "canal",
                            "description": "ID do canal obrigatório"},
    "required_channel_link": {"value": "", "type": "string", "category": "canal",
                              "description": "Link do canal"},
    "required_channel_message": {"value": "", "type": "string", "category": "canal",
                                 "description": "Mensagem de exigência"},
    "required_channel_button_text": {"value": "➡️ ENTRAR NO CANAL",
                                     "type": "string", "category": "canal",
                                     "description": "Texto do botão"},

    # Pix
    "pix_min": {"value": "4.00", "type": "float", "category": "pix",
                "description": "Valor mínimo de recarga"},
    "pix_max": {"value": "500.00", "type": "float", "category": "pix",
                "description": "Valor máximo de recarga"},
    "pix_expiration_minutes": {"value": "10", "type": "int", "category": "pix",
                               "description": "Expiração do Pix em minutos"},
    "pix_bonus_percent": {"value": "0", "type": "float", "category": "pix",
                          "description": "Percentual de bônus"},
    "pix_bonus_min": {"value": "0", "type": "float", "category": "pix",
                      "description": "Valor mínimo pra ganhar bônus"},
    "pix_auto": {"value": "true", "type": "bool", "category": "pix",
                 "description": "Pix automático (Mercado Pago)?"},

    # Afiliados
    "affiliate_enabled": {"value": "true", "type": "bool", "category": "afiliados",
                          "description": "Sistema de afiliados ativo?"},
    "affiliate_commission": {"value": "20.0", "type": "float",
                             "category": "afiliados",
                             "description": "Comissão % do afiliado"},
    "affiliate_points_per_recharge": {"value": "1", "type": "int",
                                      "category": "afiliados",
                                      "description": "Pontos por recarga"},
    "affiliate_min_points": {"value": "500", "type": "int", "category": "afiliados",
                             "description": "Mínimo de pontos pra converter"},
    "affiliate_multiplier": {"value": "0.01", "type": "float",
                             "category": "afiliados",
                             "description": "Multiplicador de pontos"},
    "affiliate_min_withdrawal": {"value": "20.00", "type": "float",
                                 "category": "afiliados",
                                 "description": "Saque mínimo"},

    # Saques
    "withdrawal_auto": {"value": "false", "type": "bool", "category": "saques",
                        "description": "Aprovação automática de saque?"},
    "withdrawal_fee_percent": {"value": "0", "type": "float", "category": "saques",
                               "description": "Taxa de saque em %"},

    # Anti-flood
    "antiflood_enabled": {"value": "true", "type": "bool", "category": "antiflood",
                          "description": "Anti-flood ativo?"},
    "antiflood_max_messages": {"value": "20", "type": "int", "category": "antiflood",
                               "description": "Máximo de mensagens"},
    "antiflood_window_seconds": {"value": "10", "type": "int", "category": "antiflood",
                                 "description": "Janela em segundos"},
    "antiflood_block_seconds": {"value": "600", "type": "int", "category": "antiflood",
                                "description": "Duração do bloqueio"},
    "antiflood_message": {"value": "", "type": "string", "category": "antiflood",
                          "description": "Mensagem de bloqueio"},

    # Bônus de registro
    "register_bonus": {"value": "0.00", "type": "float", "category": "geral",
                       "description": "Bônus por se registrar"},

    # Pesquisa
    "search_enabled": {"value": "true", "type": "bool", "category": "pesquisa",
                       "description": "Pesquisa ativa?"},
    "search_max_results": {"value": "10", "type": "int", "category": "pesquisa",
                           "description": "Máximo de resultados"},

    # Rankings
    "ranking_period_days": {"value": "30", "type": "int", "category": "ranking",
                            "description": "Período dos rankings em dias"},
    "ranking_size": {"value": "10", "type": "int", "category": "ranking",
                     "description": "Quantidade de posições"},
}


# ============================================
# 🔎 LEITURA
# ============================================
async def get_config(
    session: AsyncSession,
    key: str,
    default: Optional[Any] = None,
) -> Optional[str]:
    """Retorna o valor bruto (string) de uma config."""
    stmt = select(Config).where(Config.key == key)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if config is not None:
        return config.value

    # Cria do default se existir
    if key in DEFAULTS:
        d = DEFAULTS[key]
        new_cfg = Config(
            key=key,
            value=str(d["value"]),
            value_type=d["type"],
            category=d["category"],
            description=d.get("description"),
        )
        session.add(new_cfg)
        await session.flush()
        return new_cfg.value

    return str(default) if default is not None else None


async def get_str(session: AsyncSession, key: str, default: str = "") -> str:
    value = await get_config(session, key)
    return value if value is not None else default


async def get_int(session: AsyncSession, key: str, default: int = 0) -> int:
    value = await get_config(session, key)
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


async def get_float(session: AsyncSession, key: str, default: float = 0.0) -> float:
    value = await get_config(session, key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def get_decimal(session: AsyncSession, key: str, default: str = "0.00") -> Decimal:
    value = await get_config(session, key)
    if value is None or value == "":
        value = default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


async def get_bool(session: AsyncSession, key: str, default: bool = False) -> bool:
    value = await get_config(session, key)
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes", "on", "sim")


# ============================================
# 🧾 LEITURA EM LOTE
# ============================================
async def get_many(
    session: AsyncSession,
    keys: list[str],
) -> dict[str, Optional[str]]:
    """Busca várias configs de uma vez."""
    stmt = select(Config).where(Config.key.in_(keys))
    result = await session.execute(stmt)
    rows = {c.key: c.value for c in result.scalars().all()}

    # Preenche os que faltam
    for k in keys:
        if k not in rows and k in DEFAULTS:
            rows[k] = await get_config(session, k)

    return rows


async def get_by_category(
    session: AsyncSession,
    category: str,
) -> dict[str, Optional[str]]:
    """Busca todas as configs de uma categoria."""
    stmt = select(Config).where(Config.category == category)
    result = await session.execute(stmt)
    return {c.key: c.value for c in result.scalars().all()}


# ============================================
# ✏️ ESCRITA
# ============================================
async def set_config(
    session: AsyncSession,
    key: str,
    value: Any,
) -> Config:
    """Define (cria ou atualiza) uma config."""
    stmt = select(Config).where(Config.key == key)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    str_value = str(value)

    if config is None:
        d = DEFAULTS.get(key, {})
        config = Config(
            key=key,
            value=str_value,
            value_type=d.get("type", "string"),
            category=d.get("category", "geral"),
            description=d.get("description"),
        )
        session.add(config)
    else:
        config.value = str_value
        session.add(config)

    await session.flush()
    logger.info(f"⚙️ Config atualizada: {key} = {str_value}")
    return config


async def set_many(
    session: AsyncSession,
    data: dict[str, Any],
) -> None:
    """Define várias configs de uma vez."""
    for key, value in data.items():
        await set_config(session, key, value)


async def delete_config(session: AsyncSession, key: str) -> bool:
    """Remove uma config. Retorna True se removeu."""
    stmt = select(Config).where(Config.key == key)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    if config is None:
        return False
    await session.delete(config)
    return True


# ============================================
# 🔄 TOGGLE (liga/desliga boolean)
# ============================================
async def toggle_bool(
    session: AsyncSession,
    key: str,
    default: bool = False,
) -> bool:
    """Inverte o valor de uma config booleana. Retorna o novo valor."""
    current = await get_bool(session, key, default)
    new_value = not current
    await set_config(session, key, "true" if new_value else "false")
    return new_value


# ============================================
# 📋 LISTAGEM
# ============================================
async def list_all(session: AsyncSession) -> list[Config]:
    """Lista todas as configs."""
    stmt = select(Config).order_by(Config.category, Config.key)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_categories(session: AsyncSession) -> list[str]:
    """Lista categorias distintas."""
    stmt = select(Config.category).distinct().order_by(Config.category)
    result = await session.execute(stmt)
    return [r for r in result.scalars().all() if r]
