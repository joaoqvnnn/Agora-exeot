# ============================================
# 📦 PACOTE: core.services
# ============================================
# Serviços (regras de negócio) do sistema.
#
# Estrutura:
#   core/services/
#   ├── __init__.py       ← este arquivo
#   ├── messages.py       ← renderiza mensagens editáveis
#   ├── config.py         ← lê/grava configs
#   ├── stock.py          ← reserva e entrega de estoque
#   ├── pix.py            ← Mercado Pago (Pix real)
#   ├── payment.py        ← confirma pagamento + crédito
#   ├── delivery.py       ← entrega (Telegram/WhatsApp/E-mail)
#   ├── email.py          ← envio de e-mail SMTP
#   ├── whatsapp.py       ← API WhatsApp (não oficial)
#   ├── ai.py             ← OpenAI (atendimento)
#   ├── ranking.py        ← rankings
#   ├── affiliate.py      ← comissões e pontos
#   ├── giftcard.py       ← gift cards
#   ├── withdrawal.py     ← saques
#   ├── antiflood.py      ← leitura de configs do antiflood
#   └── audit.py          ← registro de auditoria
# ============================================
