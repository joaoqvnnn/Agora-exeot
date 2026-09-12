# ============================================
# 🧠 STATES — Larizinha Store
# ============================================
# Todos os estados FSM do bot cliente.
# Cada fluxo que espera texto/valor do usuário
# tem um estado associado aqui.
# ============================================

from aiogram.fsm.state import State, StatesGroup


# ============================================
# 💳 RECARGA DE SALDO
# ============================================
class RechargeStates(StatesGroup):
    waiting_amount = State()          # Aguardando valor da recarga
    waiting_custom_amount = State()   # Aguardando valor personalizado
    waiting_bonus_confirm = State()   # Aguardando confirmação de bônus


# ============================================
# 🛒 COMPRA DE PRODUTO
# ============================================
class PurchaseStates(StatesGroup):
    waiting_quantity = State()        # Aguardando quantidade de logins
    confirming = State()              # Aguardando confirmação
    choosing_delivery = State()       # Escolhendo entrega (telegram/zap/email)
    waiting_email = State()           # Aguardando e-mail pra entrega
    waiting_whatsapp = State()        # Aguardando WhatsApp pra entrega
    waiting_email_code = State()      # Aguardando código de verificação


# ============================================
# 🎁 GIFT CARD
# ============================================
class GiftCardStates(StatesGroup):
    waiting_code = State()            # Aguardando código do gift card


# ============================================
# 👤 PERFIL / ALTERAÇÃO DE DADOS
# ============================================
class ProfileStates(StatesGroup):
    changing_whatsapp = State()       # Aguardando novo WhatsApp
    changing_email = State()          # Aguardando novo e-mail
    waiting_email_code = State()      # Aguardando código do e-mail


# ============================================
# 🤝 AFILIADOS
# ============================================
class AffiliateStates(StatesGroup):
    registering_password = State()    # Cadastrando senha de saque
    confirming_password = State()     # Confirmando senha de saque
    registering_email = State()       # Cadastrando e-mail pra recuperação
    waiting_recovery_code = State()   # Aguardando código de recuperação
    waiting_new_password = State()    # Aguardando nova senha


# ============================================
# 💸 SAQUES
# ============================================
class WithdrawalStates(StatesGroup):
    choosing_method = State()         # Pix ou banco
    choosing_pix_type = State()       # Tipo de chave Pix
    waiting_pix_key = State()         # Aguardando chave Pix
    confirming_withdrawal = State()   # Confirmando saque
    waiting_password = State()        # Aguardando senha de saque
    waiting_email_code = State()      # Código por e-mail
    filling_bank_data = State()       # Dados bancários
    waiting_bank_password = State()   # Senha antes de transferir


# ============================================
# 🔎 PESQUISA DE SERVIÇOS
# ============================================
class SearchStates(StatesGroup):
    waiting_query = State()           # Aguardando texto da pesquisa


# ============================================
# 🎧 ATENDIMENTO
# ============================================
class SupportStates(StatesGroup):
    in_chat = State()                 # Dentro do chat de atendimento
    waiting_message = State()         # Aguardando mensagem pro humano
    human_handoff = State()           # Humano assumiu


# ============================================
# 🔔 ALERTAS DE ESTOQUE
# ============================================
class AlertStates(StatesGroup):
    managing = State()                # Gerenciando alertas


# ============================================
# 👮 ADMIN — ESTADOS DO PAINEL
# ============================================
class AdminStates(StatesGroup):
    # Gerais
    waiting_broadcast_text = State()
    waiting_broadcast_target = State()
    waiting_broadcast_schedule = State()

    # Configurações
    editing_config_value = State()
    editing_separator = State()
    editing_logs_channel = State()
    editing_support_link = State()

    # Admins
    adding_admin = State()
    removing_admin = State()

    # Produtos
    creating_product = State()
    editing_product_name = State()
    editing_product_price = State()
    editing_product_description = State()
    editing_product_image = State()
    editing_product_warranty = State()
    editing_product_duration = State()
    editing_product_min_qty = State()
    editing_product_max_qty = State()

    # Categorias
    creating_category = State()
    editing_category = State()

    # Estoque
    adding_stock = State()
    removing_stock = State()
    removing_stock_by_platform = State()
    changing_service_price = State()
    changing_all_prices = State()

    # Usuários
    searching_user = State()
    editing_user_balance = State()
    editing_user_data = State()
    sending_broadcast_user = State()

    # Pix
    editing_mp_token = State()
    editing_pix_min = State()
    editing_pix_max = State()
    editing_pix_expiration = State()
    editing_pix_bonus = State()
    editing_pix_bonus_min = State()

    # Afiliados
    editing_affiliate_points_per_recharge = State()
    editing_affiliate_min_points = State()
    editing_affiliate_multiplier = State()
    editing_affiliate_commission = State()
    editing_affiliate_min_withdrawal = State()

    # Gift cards
    creating_gift_card = State()
    creating_gift_cards_bulk = State()

    # Mensagens / Botões / Imagens
    editing_message_text = State()
    editing_message_image = State()
    editing_button_text = State()
    editing_button_url = State()
    editing_image = State()

    # Broadcast / Agendador
    scheduling_broadcast = State()

    # Manutenção
    editing_maintenance_message = State()
    editing_maintenance_return_message = State()

    # Anti-flood
    editing_antiflood_limit = State()
    editing_antiflood_window = State()
    editing_antiflood_block = State()

    # Bloqueios
    blocking_user = State()
    blocking_user_reason = State()
    blocking_user_duration = State()

    # Saques
    approving_withdrawal = State()
    rejecting_withdrawal = State()
    rejection_reason = State()

    # Configuração bancária
    editing_bank_config = State()

    # Pesquisa
    editing_search_message = State()
    adding_search_image = State()

    # Termos
    editing_terms = State()

    # Atendimento
    editing_support_link = State()
    editing_support_message = State()

    # Canal obrigatório
    editing_required_channel = State()
    editing_required_channel_message = State()

    # Comandos
    editing_command = State()

    # Confirmação genérica
    confirming_action = State()
