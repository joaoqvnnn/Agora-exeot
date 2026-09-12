# ============================================
# 📝 MESSAGES — Larizinha Store
# ============================================
# Renderiza mensagens editáveis do banco (message_templates).
# Substitui variáveis {USER_ID}, {BALANCE}, {PRODUCT_NAME}, etc.
# Se a mensagem não existir no banco, usa fallback padrão e
# CRIA automaticamente pra o admin poder editar depois.
# ============================================

import re
from decimal import Decimal
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import MessageTemplate


# ============================================
# 📚 FALLBACKS PADRÃO
# ============================================
# Se a mensagem não existir no banco, usa um destes
# e cria no banco pra o admin editar.
# ============================================
DEFAULT_MESSAGES: dict[str, dict[str, str]] = {
    "start": {
        "category": "start",
        "title": "Mensagem de /start",
        "text": (
            "🎬 <b>Bem-vindo à {BOT_NAME}!</b> ✨\n"
            "A sua central de streamings com entrega 100% automática.\n\n"
            "Pagou, recebeu. Sem filas, sem precisar falar com atendente, "
            "24 horas por dia! ⚡️\n\n"
            "🛡 <b>Segurança e Suporte:</b>\n"
            "Mais de 12.000 clientes já passaram por aqui.\n"
            "Participe da nossa comunidade e veja as referências\n\n"
            "💠 <b>Seus Dados:</b>\n"
            "├👤 ID: <code>{USER_ID}</code>\n"
            "└💰 Saldo Atual: <b>R$ {BALANCE}</b>\n\n"
            "👇 <b>COMO COMEÇAR:</b>\n"
            'Clique no botão "🛍 Comprar Produtos" abaixo para ver '
            "nosso catálogo e escolher sua tela!"
        ),
    },
    "sobre": {
        "category": "start",
        "title": "Sobre o bot",
        "text": (
            "ℹ️ <b>Sobre a {BOT_NAME}</b>\n\n"
            "Somos uma central de streamings com entrega automática.\n"
            "Pagamento via Pix, entrega na hora, suporte 24h.\n\n"
            "📌 Use /termos para ver os termos de uso."
        ),
    },
    "catalogo": {
        "category": "catalogo",
        "title": "Catálogo de serviços",
        "text": (
            "📱 <b>{BOT_NAME} | Catálogo de Serviços</b>\n"
            "🔗🔗🔗🔗🔗🔗🔗🔗🔗🔗🔗\n\n"
            "💰| Saldo da Carteira: <b>R$ {BALANCE}</b>\n\n"
            "⬇️ Selecione uma categoria abaixo para ver nossos planos:"
        ),
    },
    "catalogo_vazio": {
        "category": "catalogo",
        "title": "Catálogo vazio",
        "text": (
            "📱 <b>Catálogo</b>\n\n"
            "⚠️ Nenhuma categoria disponível no momento.\n"
            "Volte mais tarde!"
        ),
    },
    "produto": {
        "category": "produto",
        "title": "Tela do produto",
        "text": (
            "🔥 <b>OPORTUNIDADE EXCLUSIVA</b> 🔥\n"
            "🚀 <b>{PRODUCT_NAME}</b>\n\n"
            "🟢 <b>DISPONÍVEL AGORA</b>\n"
            "├ 💵 Preço: <b>R$ {PRODUCT_PRICE}</b>\n"
            "├ 💰 Seu Saldo: <b>R$ {BALANCE}</b>\n"
            "└ 📦 Estoque: <b>{STOCK}</b>\n\n"
            "📝 <b>Descrição:</b>\n{PRODUCT_DESCRIPTION}\n\n"
            "📊 <b>Estatísticas em tempo real:</b>\n"
            "⚡️ Já foram vendidas <b>{PRODUCT_SOLD}</b> unidades!\n"
            "👀 <b>{VIEWERS}</b> pessoas estão vendo isso agora.\n\n"
            "🛡 Garantia: <b>{WARRANTY} dias</b>\n"
            "✅ Compra segura. Ao adquirir, concorda com /termos"
        ),
    },
    "produto_esgotado": {
        "category": "produto",
        "title": "Produto esgotado",
        "text": (
            "🚀 <b>{PRODUCT_NAME}</b>\n\n"
            "❌ <b>ESGOTADO</b>\n\n"
            "Infelizmente este produto está sem estoque no momento.\n"
            "Clique no botão abaixo para ser avisado quando voltar."
        ),
    },
    "saldo_insuficiente": {
        "category": "compra",
        "title": "Saldo insuficiente",
        "text": (
            "❌ <b>Saldo insuficiente!</b>\n\n"
            "💰 Seu saldo: <b>R$ {BALANCE}</b>\n"
            "💵 Valor do produto: <b>R$ {PRODUCT_PRICE}</b>\n"
            "📉 Faltam: <b>R$ {MISSING}</b>\n\n"
            "💡 Deseja gerar um PIX no valor de <b>R$ {MISSING}</b> "
            "para completar a compra?"
        ),
    },
    "saldo_insuficiente_total": {
        "category": "compra",
        "title": "Saldo insuficiente (múltipla)",
        "text": (
            "❌ <b>Saldo insuficiente!</b>\n\n"
            "💰 Seu saldo: <b>R$ {BALANCE}</b>\n"
            "💵 Valor total: <b>R$ {TOTAL}</b>\n"
            "📉 Faltam: <b>R$ {MISSING}</b>\n\n"
            "💡 Deseja gerar um PIX para completar a compra?"
        ),
    },
    "pergunta_quantidade": {
        "category": "compra",
        "title": "Pergunta de quantidade",
        "text": (
            "Quantos logins deseja comprar?\n\n"
            "📦 Estoque disponível: <b>{STOCK}</b>\n\n"
            "💡 Digite /cancelar a qualquer momento para sair."
        ),
    },
    "compra_cancelada": {
        "category": "compra",
        "title": "Compra cancelada",
        "text": (
            "❌ <b>Compra cancelada!</b>\n\n"
            "Operação de compra múltipla foi cancelada."
        ),
    },
    "valor_invalido": {
        "category": "erros",
        "title": "Valor inválido",
        "text": (
            "❌ <b>Valor inválido!</b> Envie apenas números.\n"
            "Exemplo: <code>10</code> ou <code>25.50</code>"
        ),
    },
    "gerando_pagamento": {
        "category": "pix",
        "title": "Gerando pagamento",
        "text": "⏳ <b>Gerando pagamento...</b>",
    },
    "pix_gerado": {
        "category": "pix",
        "title": "Pix gerado",
        "text": (
            "💰 <b>Comprar Saldo com Pix Automático:</b>\n\n"
            "⏱️ Expira em: <b>{EXPIRATION} Minutos</b>\n"
            "💵 Valor: <b>R$ {AMOUNT}</b>\n"
            "✨ ID da Recarga: <code>{PAYMENT_ID}</code>\n\n"
            "📃 <b>Atenção:</b> Este código é válido para apenas "
            "um único pagamento. Se você utilizá-lo mais de uma vez, "
            "o saldo adicional será perdido sem direito a reembolso.\n\n"
            "💎 <b>Pix Copia e Cola:</b>\n"
            "<code>{PIX_CODE}</code>\n\n"
            "💡 <b>Dica:</b> Clique no código acima para copiar.\n\n"
            "📊 <b>Dados:</b>\n"
            "— 💰 Saldo Atual: <b>R$ {BALANCE}</b>\n"
            "— 🎁 Bônus à receber: <b>R$ {BONUS}</b>\n"
            "— 💸 Saldo após o pagamento: <b>R$ {AFTER}</b>\n\n"
            "🇧🇷 Após o pagamento, seu saldo será liberado instantaneamente."
        ),
    },
    "pix_expirado": {
        "category": "pix",
        "title": "Pix expirado",
        "text": (
            "⌛️ <b>PAGAMENTO PIX EXPIRADO</b>\n\n"
            "⚠️ O tempo limite para realizar este pagamento foi excedido.\n\n"
            "🆔 Referência do Pagamento: <code>{PAYMENT_ID}</code>\n"
            "💸 Valor Solicitado: <b>R$ {AMOUNT}</b>"
        ),
    },
    "pagamento_aprovado": {
        "category": "pix",
        "title": "Pagamento aprovado",
        "text": (
            "✅ <b>Pagamento realizado com sucesso!</b>\n\n"
            "💰 Valor creditado: <b>R$ {AMOUNT}</b>\n"
            "🎁 Bônus: <b>R$ {BONUS}</b>\n"
            "💸 Saldo atual: <b>R$ {BALANCE}</b>\n\n"
            "⏰ Data: {DATE}\n"
            "🆔 Transação: <code>{PAYMENT_ID}</code>"
        ),
    },
    "canal_obrigatorio": {
        "category": "canal",
        "title": "Canal obrigatório",
        "text": (
            "❗️ <b>Para utilizar nosso serviço é obrigatório que "
            "você entre no nosso grupo.</b>\n\n"
            "➡️ Entre no canal abaixo:"
        ),
    },
    "canal_botao": {
        "category": "canal",
        "title": "Texto do botão do canal",
        "text": "➡️ ENTRAR NO CANAL",
    },
    "perfil": {
        "category": "perfil",
        "title": "Meu perfil",
        "text": (
            "👤 <b>Meu perfil</b>\n\n"
            "🔍 Veja aqui os detalhes da sua conta:\n\n"
            "- 👤 <b>Informações:</b>\n"
            "🆔 ID da Carteira: <code>{USER_ID}</code>\n"
            "💰 Saldo Atual: <b>R$ {BALANCE}</b>\n"
            "📲 Seu Whatsapp: {WHATSAPP}\n\n"
            "─── 📊 <b>Suas Movimentações:</b>\n"
            "ー 🛒 Compras Realizadas: <b>{PURCHASES}</b>\n"
            "ー 💰 Total Gasto Em Compras: <b>R$ {TOTAL_SPENT}</b>\n"
            "ー 💠 Pix Inseridos: <b>R$ {TOTAL_RECHARGED}</b>\n"
            "ー 🎁 Gifts Resgatados: <b>R$ {GIFTS}</b>"
        ),
    },
    "historico_vazio": {
        "category": "historico",
        "title": "Histórico vazio",
        "text": (
            "📜 <b>Histórico de compras</b>\n\n"
            "Você ainda não realizou nenhuma compra.\n\n"
            "🛍 Use o botão abaixo para ver nosso catálogo."
        ),
    },
    "historico_item": {
        "category": "historico",
        "title": "Item do histórico",
        "text": (
            "🛍 Compras: <b>{PURCHASES}</b>\n\n"
            "⏰ Data da compra: {DATE}\n"
            "📆 Vencimento: {EXPIRATION}\n"
            "💰 Valor: <b>R$ {AMOUNT}</b>\n"
            "🎫 ID da compra: <code>{ORDER_ID}</code>\n"
            "⚜️ Serviço: <b>{PRODUCT_NAME}</b>\n"
            "📧 Email: <code>{EMAIL}</code>\n"
            "🔐 Senha: <code>{PASSWORD}</code>\n"
            "📃 Nota: {NOTE}\n\n"
            "Ref: {REF}"
        ),
    },
    "historico_sem_ativas": {
        "category": "historico",
        "title": "Sem compras ativas",
        "text": (
            "Você não tem compras ativas (não vencidas) no bot.\n\n"
            "Use o botão abaixo para ver todas as compras."
        ),
    },
    "gift_card_pedir": {
        "category": "gift_card",
        "title": "Pedir código do gift card",
        "text": (
            "🎁 <b>RESGATAR GIFT CARD</b>\n\n"
            "Digite o código do seu gift card abaixo:\n\n"
            "Exemplo: <code>ABC123XYZ456</code>"
        ),
    },
    "gift_card_invalido": {
        "category": "gift_card",
        "title": "Gift card não encontrado",
        "text": "❌ Gift não encontrado.",
    },
    "gift_card_sucesso": {
        "category": "gift_card",
        "title": "Gift card resgatado",
        "text": (
            "🎉 <b>Gift card resgatado com sucesso!</b>\n\n"
            "💰 Valor: <b>R$ {AMOUNT}</b>\n"
            "💸 Novo saldo: <b>R$ {BALANCE}</b>"
        ),
    },
    "afiliados": {
        "category": "afiliados",
        "title": "Programa de afiliados",
        "text": (
            "💰 <b>PROGRAMA DE AFILIADOS</b>\n\n"
            "⚙️ Status: <b>{STATUS}</b>\n"
            "🧲 Sua comissão: <b>{COMMISSION}%</b> "
            "(de todas recargas do indicado)\n\n"
            "👥 Indicações: <b>{REFERRALS}</b>\n"
            "🪙 Total ganho: <b>R$ {EARNED}</b>\n"
            "📊 Média: <b>R$ {AVERAGE}</b>\n"
            "💰 Saque mínimo: <b>R$ {MIN_WITHDRAWAL}</b>\n\n"
            "🔥 Saldo de comissões: <b>R$ {AFFILIATE_BALANCE}</b>\n\n"
            "🌱| Nível: <b>{LEVEL}</b>\n"
            "🎯 Próxima meta: {NEXT_GOAL}\n\n"
            "ℹ️ <b>INFO:</b> Seus indicados continuarão gerando "
            "comissão para sempre.\n"
            "A comissão pode ser alterada a qualquer momento, "
            "fique atento aos avisos.\n"
            "🔗 Seu link:\n{REFERRAL_LINK}"
        ),
    },
    "historico_saques_vazio": {
        "category": "afiliados",
        "title": "Histórico de saques vazio",
        "text": (
            "📊 <b>HISTÓRICO DE SAQUES</b>\n\n"
            "Você ainda não solicitou nenhum saque.\n\n"
            "📉 Saque mínimo atual: <b>R$ {MIN_WITHDRAWAL}</b>"
        ),
    },
    "ranking_servicos": {
        "category": "ranking",
        "title": "Ranking de serviços",
        "text": (
            "🏆 <b>Ranking dos serviços mais vendidos (deste mês)</b>\n\n"
            "{LIST}\n\n"
            "💡 Você ainda não está no ranking."
        ),
    },
    "recarga_pedir_valor": {
        "category": "pix",
        "title": "Pedir valor da recarga",
        "text": (
            "🆔| ID da Carteira: <code>{USER_ID}</code>\n"
            "💰| Saldo Disponível: <b>R$ {BALANCE}</b>\n\n"
            "📍 Opte por 💠 Pix Rápido para que seu saldo seja "
            "creditado imediatamente.\n\n"
            "💡 Selecione uma opção para recarregar:"
        ),
    },
    "recarga_informar_valor": {
        "category": "pix",
        "title": "Informar valor da recarga",
        "text": (
            "ℹ️ <b>Informe o valor que deseja recarregar:</b>\n\n"
            "🔻 Recarga mínima: <b>R$ {MIN}</b>\n\n"
            "⚠️ Por favor, envie o valor que deseja recarregar agora.\n"
            "Ao realizar um depósito você declara ter lido e estar "
            "de acordo com nossos /termos\n\n"
            "🎁 Bônus de recarga: <b>{BONUS_PERCENT}%</b>\n"
            "❗️ Recarga mínima para ganhar o bônus: <b>R$ {BONUS_MIN}</b>"
        ),
    },
    "recarga_bonus_sugerido": {
        "category": "pix",
        "title": "Sugestão de bônus",
        "text": (
            "🎁 <b>Eiii, eu tenho algo pra você!</b>\n\n"
            "Recarregando <b>R$ {SUGGESTED}</b> você ganha acesso a "
            "mais <b>{BONUS_PERCENT}%</b> de bônus "
            "(+R$ {BONUS_VALUE}), tem certeza que vai perder essa?\n\n"
            "💡 Faltam apenas <b>R$ {MISSING}</b> para ganhar o bônus!"
        ),
    },
    "manutencao": {
        "category": "manutencao",
        "title": "Mensagem de manutenção",
        "text": (
            "🔧 <b>BOT EM MANUTENÇÃO</b>\n"
            "Estamos realizando uma manutenção. "
            "Tente novamente mais tarde."
        ),
    },
    "manutencao_retorno": {
        "category": "manutencao",
        "title": "Mensagem de retorno",
        "text": (
            "🟢 <b>BOT ONLINE</b>\n"
            "A manutenção foi finalizada. "
            "O bot já está funcionando normalmente!"
        ),
    },
    "antiflood_bloqueio": {
        "category": "erros",
        "title": "Bloqueio anti-flood",
        "text": (
            "🚫 <b>Você foi bloqueado por flood.</b>\n\n"
            "Aguarde <b>{tempo}</b> para voltar a usar o bot."
        ),
    },
}


# ============================================
# 🎨 RENDER
# ============================================
async def render_message(
    session: AsyncSession,
    key: str,
    variables: Optional[dict[str, Any]] = None,
) -> str:
    """
    Busca a mensagem no banco e substitui as variáveis.
    Se não existir, cria a partir do DEFAULT_MESSAGES.
    """
    template = await _get_or_create_template(session, key)

    text = template.text
    if variables:
        text = _substitute(text, variables)

    return text


async def get_template(
    session: AsyncSession,
    key: str,
) -> Optional[MessageTemplate]:
    """Retorna o template sem renderizar."""
    stmt = select(MessageTemplate).where(MessageTemplate.key == key)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_or_create_template(
    session: AsyncSession,
    key: str,
) -> MessageTemplate:
    """Busca no banco; se não existir, cria com o padrão."""
    template = await get_template(session, key)

    if template is not None:
        return template

    default = DEFAULT_MESSAGES.get(key)
    if default is None:
        logger.warning(f"⚠️ Mensagem '{key}' não encontrada e sem fallback.")
        template = MessageTemplate(
            key=key,
            category="geral",
            title=key,
            text="⚠️ Mensagem não configurada.",
        )
    else:
        template = MessageTemplate(
            key=key,
            category=default["category"],
            title=default["title"],
            text=default["text"],
        )

    session.add(template)
    await session.flush()
    logger.info(f"📝 Mensagem criada com padrão: {key}")
    return template


# ============================================
# 🔤 SUBSTITUIÇÃO DE VARIÁVEIS
# ============================================
_VAR_PATTERN = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")


def _substitute(text: str, variables: dict[str, Any]) -> str:
    """Substitui {VAR} pelos valores. Aceita Decimal, int, str."""

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name in variables:
            value = variables[name]
            if isinstance(value, Decimal):
                return f"{value:.2f}".replace(".", ",")
            if isinstance(value, float):
                return f"{value:.2f}".replace(".", ",")
            return str(value)
        return match.group(0)  # mantém {VAR} se não achar

    return _VAR_PATTERN.sub(_replace, text)
