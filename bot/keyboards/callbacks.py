# ============================================
# 🔘 CALLBACKS — Larizinha Store
# ============================================
# Fábricas de callback_data usando CallbackData
# do aiogram 3. Cada botão tem um formato próprio
# e tipado, evitando erros de string solta.
#
# Uso:
#   await callback.answer()
#   data = MenuCallback.unpack(callback.data)
#   if data.action == "catalogo":
#       ...
# ============================================

from aiogram.filters.callback_data import CallbackData


# ============================================
# 🏠 MENU PRINCIPAL
# ============================================
class MenuCallback(CallbackData, prefix="menu"):
    """Botões do menu /start."""
    action: str  # comprar, loja, perfil, recarregar, afiliados,
                 # ranking, atendimento, sobre, pesquisa, voltar


# ============================================
# 📂 CATÁLOGO / CATEGORIAS
# ============================================
class CatalogCallback(CallbackData, prefix="cat"):
    """Navegação do catálogo."""
    action: str              # open, page, back, voltar
    category_id: int = 0
    page: int = 0


# ============================================
# 📦 PRODUTO
# ============================================
class ProductCallback(CallbackData, prefix="prod"):
    """Ações dentro de um produto."""
    action: str              # view, buy, buy_now, quantity, back
    product_id: int
    quantity: int = 1


# ============================================
# 💳 PIX / RECARGA
# ============================================
class PixCallback(CallbackData, prefix="pix"):
    """Botões de Pix."""
    action: str              # gerar, cancelar, copiar, verificar, voltar
    amount: str = "0"        # valor em string pra não perder precisão
    payment_id: str = ""


# ============================================
# 🛒 COMPRA
# ============================================
class PurchaseCallback(CallbackData, prefix="buy"):
    """Botões do fluxo de compra."""
    action: str              # confirm, cancel, quantity_ok, delivery
    product_id: int = 0
    quantity: int = 1
    payment_id: str = ""


# ============================================
# 👤 PERFIL
# ============================================
class ProfileCallback(CallbackData, prefix="prof"):
    """Botões do perfil."""
    action: str              # historico, gift, alterar, voltar,
                             # historico_page, historico_filter


# ============================================
# 🎁 GIFT CARD
# ============================================
class GiftCallback(CallbackData, prefix="gift"):
    """Botões do gift card."""
    action: str              # resgatar, cancelar, voltar


# ============================================
# 🤝 AFILIADOS
# ============================================
class AffiliateCallback(CallbackData, prefix="aff"):
    """Botões do menu de afiliados."""
    action: str              # historico, cadastrar_banco, cadastrar_pix,
                             # cadastrar_senha, cadastrar_email, saque,
                             # saque_pix, saque_banco, voltar


# ============================================
# 💸 SAQUES
# ============================================
class WithdrawalCallback(CallbackData, prefix="wd"):
    """Botões do fluxo de saque."""
    action: str              # pix, banco, confirmar, cancelar,
                             # tipo_pix, editar_chave, digitar_senha
    pix_type: str = ""       # cpf, cnpj, email, phone, random


# ============================================
# 🏆 RANKING
# ============================================
class RankingCallback(CallbackData, prefix="rank"):
    """Botões do ranking."""
    action: str              # servicos, recargas, compras, saldo, voltar


# ============================================
# 🔔 ALERTAS
# ============================================
class AlertCallback(CallbackData, prefix="alert"):
    """Botões de alertas de estoque."""
    action: str              # toggle, next_page, prev_page, voltar
    product_id: int = 0
    page: int = 0


# ============================================
# 🔎 PESQUISA
# ============================================
class SearchCallback(CallbackData, prefix="search"):
    """Botões da pesquisa."""
    action: str              # open, view, comprar, voltar
    product_id: int = 0


# ============================================
# 🎧 ATENDIMENTO
# ============================================
class SupportCallback(CallbackData, prefix="sup"):
    """Botões de atendimento."""
    action: str              # open, humano, fechar, voltar


# ============================================
# 📜 TERMOS
# ============================================
class TermsCallback(CallbackData, prefix="terms"):
    """Botões dos termos."""
    action: str              # view, aceitar, voltar


# ============================================
# 👮 ADMIN — PAINEL
# ============================================
class AdminCallback(CallbackData, prefix="adm"):
    """Navegação geral do painel admin."""
    action: str              # dashboard, configuracoes, acoes,
                             # transacoes, atualizacoes, voltar


class AdminConfigCallback(CallbackData, prefix="adm_cfg"):
    """Configurações do painel admin."""
    action: str              # gerais, admins, afiliados, usuarios,
                             # pix, logins, pesquisa, separador,
                             # destino_log, manutencao, voltar


class AdminProductCallback(CallbackData, prefix="adm_prod"):
    """Gerenciamento de produtos no admin."""
    action: str              # add, edit, remove, list, price, position
    product_id: int = 0


class AdminStockCallback(CallbackData, prefix="adm_stock"):
    """Gerenciamento de estoque no admin."""
    action: str              # add, remove, remove_platform, clear,
                             # details, change_price, change_all
    product_id: int = 0


class AdminUserCallback(CallbackData, prefix="adm_user"):
    """Gerenciamento de usuários no admin."""
    action: str              # search, view, add_balance, remove_balance,
                             # block, unblock, history, broadcast
    user_id: int = 0


class AdminPixCallback(CallbackData, prefix="adm_pix"):
    """Configurações de Pix no admin."""
    action: str              # token, min, max, expiration, bonus,
                             # bonus_min, manual, auto, voltar


class AdminMessageCallback(CallbackData, prefix="adm_msg"):
    """Editor de mensagens no admin."""
    action: str              # list, edit, reset, preview, image
    key: str = ""


class AdminButtonCallback(CallbackData, prefix="adm_btn"):
    """Editor de botões no admin."""
    action: str              # list, edit_text, edit_url, edit_position,
                             # toggle, add, remove
    key: str = ""
    menu: str = ""


class AdminImageCallback(CallbackData, prefix="adm_img"):
    """Editor de imagens no admin."""
    action: str              # list, add, remove, view
    key: str = ""


class AdminBroadcastCallback(CallbackData, prefix="adm_bc"):
    """Broadcast no admin."""
    action: str              # new, send_now, schedule, target,
                             # confirm, cancel, list
    broadcast_id: int = 0


class AdminGiftCallback(CallbackData, prefix="adm_gift"):
    """Gift cards no admin."""
    action: str              # create, bulk, list, revoke
    gift_id: int = 0


class AdminWithdrawalCallback(CallbackData, prefix="adm_wd"):
    """Saques no admin."""
    action: str              # list, approve, reject, view
    withdrawal_id: int = 0


class AdminBlockCallback(CallbackData, prefix="adm_block"):
    """Bloqueios no admin."""
    action: str              # list, block, unblock, duration
    user_id: int = 0


class AdminMaintenanceCallback(CallbackData, prefix="adm_maint"):
    """Manutenção no admin."""
    action: str              # toggle, edit_message, edit_return


class AdminAntifloodCallback(CallbackData, prefix="adm_af"):
    """Anti-flood no admin."""
    action: str              # toggle, limit, window, block, message


class AdminTermsCallback(CallbackData, prefix="adm_terms"):
    """Termos no admin."""
    action: str              # edit, view


class AdminLogsCallback(CallbackData, prefix="adm_logs"):
    """Logs no admin."""
    action: str              # list, filter, export


class AdminTransactionCallback(CallbackData, prefix="adm_tx"):
    """Transações no admin."""
    action: str              # list, filter, view, export
    filter_type: str = ""


class AdminUpdatesCallback(CallbackData, prefix="adm_upd"):
    """Atualizações no admin."""
    action: str              # check, restart, status, logs


# ============================================
# ✅ CONFIRMAÇÃO GENÉRICA
# ============================================
class ConfirmCallback(CallbackData, prefix="confirm"):
    """Botões de confirmação genéricos."""
    action: str              # yes, no
    context: str = ""        # qual ação está confirmando
    target_id: str = ""


# ============================================
# 📄 PAGINAÇÃO GENÉRICA
# ============================================
class PaginationCallback(CallbackData, prefix="page"):
    """Paginação reutilizável."""
    context: str             # qual lista está paginando
    page: int
    extra: str = ""
