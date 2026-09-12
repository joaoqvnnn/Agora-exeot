# ============================================
# 📧 EMAIL SERVICE — Larizinha Store
# ============================================
# Envio de e-mail via SMTP (assíncrono).
# Templates HTML com Jinja2 + design profissional.
#
# Fluxos:
#   - Código de verificação
#   - Entrega de produto com LINK DE ACESSO
#   - Recuperação de senha de saque
#   - Comprovante de compra
#   - Notificação de pagamento aprovado
#   - Confirmação de e-mail
# ============================================

import secrets
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from decimal import Decimal
from typing import Any, Optional

import aiosmtplib
from jinja2 import Template
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import Order, StockItem, User


# ============================================
# 📤 ENVIO BASE
# ============================================
async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    from_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Envia e-mail via SMTP.
    Retorna dict com sucesso e erro (se houver).
    """
    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("⚠️ SMTP não configurado.")
        return {"success": False, "error": "SMTP não configurado."}

    from_email = settings.smtp_from_email or settings.smtp_user
    sender_name = from_name or settings.smtp_from_name or "Larizinha Store"

    message = MIMEMultipart("alternative")
    message["From"] = f"{sender_name} <{from_email}>"
    message["To"] = to_email
    message["Subject"] = subject

    if text_body:
        message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=settings.smtp_use_tls,
            timeout=30,
        )
        logger.info(f"📧 E-mail enviado para {to_email}: {subject}")
        return {"success": True}
    except aiosmtplib.SMTPException as e:
        logger.error(f"❌ Erro SMTP ao enviar para {to_email}: {e}")
        return {"success": False, "error": f"SMTP: {e}"}
    except Exception as e:
        logger.exception(f"❌ Erro inesperado ao enviar e-mail: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# 🔐 CÓDIGO DE VERIFICAÇÃO
# ============================================
def generate_verification_code(length: int = 6) -> str:
    """Gera código numérico de N dígitos."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


async def send_verification_code(
    to_email: str,
    code: str,
    purpose: str = "Verificação",
) -> dict[str, Any]:
    """Envia código de verificação por e-mail."""
    subject = f"🔐 Seu código de {purpose}"

    html = _render_template(
        VERIFICATION_TEMPLATE,
        {
            "code": code,
            "purpose": purpose,
            "year": datetime.now().year,
            "bot_name": "Larizinha Store",
        },
    )

    text = (
        f"Seu código de {purpose} é: {code}\n\n"
        f"Válido por 15 minutos.\n"
        f"Não compartilhe com ninguém."
    )

    return await send_email(to_email, subject, html, text)


# ============================================
# 📦 ENTREGA DE PRODUTO COM LINK DE ACESSO
# ============================================
async def send_product_email(
    session: AsyncSession,
    to_email: str,
    user: User,
    order: Order,
    items: list[StockItem],
) -> dict[str, Any]:
    """
    Envia o produto por e-mail com LINK DE ACESSO
    pro website de ativação.

    IMPORTANTE:
      - O link NÃO é enviado no Telegram
      - O token tem assinatura HMAC (segurança)
      - Expira em 30 dias (configurável)
      - Ao clicar, o cliente informa a senha de saque
    """
    # Gera token de ativação (com assinatura HMAC-SHA256)
    from api.routes.activation import generate_activation_token

    activation_token = generate_activation_token(order.order_code)

    # URL completa de ativação
    activation_url = f"{settings.activation_url.rstrip('/')}/{activation_token}"

    # Marca data de entrega (usada pro cálculo de expiração)
    if not order.delivered_at:
        order.delivered_at = datetime.now(timezone.utc)
        session.add(order)
        await session.flush()

    # Formata dados
    date_str = (
        order.created_at.strftime("%d/%m/%Y") if order.created_at else "N/A"
    )
    exp_str = (
        order.expires_at.strftime("%d/%m/%Y") if order.expires_at else "N/A"
    )
    valor = f"{order.total_price:.2f}".replace(".", ",")

    subject = f"📦 Seu produto está pronto - {order.product_name}"

    html = _render_template(
        PRODUCT_DELIVERY_TEMPLATE,
        {
            "user_name": user.first_name or "Cliente",
            "product_name": order.product_name,
            "order_code": order.order_code,
            "date": date_str,
            "expiration": exp_str,
            "value": valor,
            "quantity": order.quantity,
            "activation_url": activation_url,
            "year": datetime.now().year,
            "bot_name": "Larizinha Store",
        },
    )

    text = (
        f"📦 Seu produto está pronto!\n\n"
        f"Produto: {order.product_name}\n"
        f"Pedido: {order.order_code}\n"
        f"Valor: R$ {valor}\n"
        f"Quantidade: {order.quantity}\n\n"
        f"Para acessar, clique no link abaixo:\n\n"
        f"{activation_url}\n\n"
        f"Você precisará digitar sua senha de saque cadastrada."
    )

    result = await send_email(to_email, subject, html, text)

    if result.get("success"):
        logger.info(
            f"📧 Produto entregue por e-mail: pedido {order.order_code} "
            f"→ {to_email}"
        )
    else:
        logger.error(
            f"❌ Falha ao enviar produto por e-mail "
            f"{order.order_code} → {to_email}"
        )

    return result


# ============================================
# 🔑 RECUPERAÇÃO DE SENHA
# ============================================
async def send_password_recovery_code(
    to_email: str,
    code: str,
) -> dict[str, Any]:
    """Envia código para recuperar senha de saque."""
    subject = "🔑 Recuperação de senha"

    html = _render_template(
        RECOVERY_TEMPLATE,
        {
            "code": code,
            "year": datetime.now().year,
            "bot_name": "Larizinha Store",
        },
    )

    text = (
        f"Seu código de recuperação é: {code}\n\n"
        f"Válido por 15 minutos.\n"
        f"Se não foi você, ignore este e-mail."
    )

    return await send_email(to_email, subject, html, text)


# ============================================
# 🧾 COMPROVANTE DE COMPRA
# ============================================
async def send_purchase_receipt(
    to_email: str,
    user: User,
    order: Order,
) -> dict[str, Any]:
    """Envia comprovante de compra por e-mail."""
    valor = f"{order.total_price:.2f}".replace(".", ",")
    date_str = (
        order.created_at.strftime("%d/%m/%Y %H:%M") if order.created_at else "N/A"
    )

    subject = f"🧾 Comprovante - Pedido {order.order_code[:12]}"

    html = _render_template(
        RECEIPT_TEMPLATE,
        {
            "user_name": user.first_name or "Cliente",
            "order_code": order.order_code,
            "product_name": order.product_name,
            "quantity": order.quantity,
            "value": valor,
            "date": date_str,
            "year": datetime.now().year,
            "bot_name": "Larizinha Store",
        },
    )

    text = (
        f"Comprovante de compra\n\n"
        f"Pedido: {order.order_code}\n"
        f"Produto: {order.product_name}\n"
        f"Quantidade: {order.quantity}\n"
        f"Valor: R$ {valor}\n"
        f"Data: {date_str}"
    )

    return await send_email(to_email, subject, html, text)


# ============================================
# ✅ CONFIRMAÇÃO DE PAGAMENTO
# ============================================
async def send_payment_approved(
    to_email: str,
    user: User,
    amount: Decimal,
    new_balance: Decimal,
    payment_id: str,
) -> dict[str, Any]:
    """Envia confirmação de pagamento aprovado."""
    valor = f"{amount:.2f}".replace(".", ",")
    saldo = f"{new_balance:.2f}".replace(".", ",")
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")

    subject = "✅ Pagamento aprovado"

    html = _render_template(
        PAYMENT_APPROVED_TEMPLATE,
        {
            "user_name": user.first_name or "Cliente",
            "value": valor,
            "new_balance": saldo,
            "payment_id": payment_id,
            "date": date_str,
            "year": datetime.now().year,
            "bot_name": "Larizinha Store",
        },
    )

    text = (
        f"Pagamento aprovado!\n\n"
        f"Valor: R$ {valor}\n"
        f"Novo saldo: R$ {saldo}\n"
        f"ID: {payment_id}\n"
        f"Data: {date_str}"
    )

    return await send_email(to_email, subject, html, text)


# ============================================
# 🎨 TEMPLATES HTML (design profissional)
# ============================================
_BASE_STYLE = """
<style>
  * { box-sizing: border-box; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
    background: #0a0a0f;
    margin: 0;
    padding: 32px 16px;
    color: #e6e6e6;
    -webkit-font-smoothing: antialiased;
  }
  .wrapper {
    max-width: 560px;
    margin: 0 auto;
  }
  .card {
    background: linear-gradient(180deg, #14141c 0%, #1c1c28 100%);
    border-radius: 20px;
    padding: 40px 32px;
    border: 1px solid #2a2a3a;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
  }
  .logo {
    width: 64px;
    height: 64px;
    border-radius: 20px;
    background: linear-gradient(135deg, #7c5cff, #4f46e5);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 32px;
    margin: 0 auto 24px;
    box-shadow: 0 8px 32px rgba(124, 92, 255, 0.4);
  }
  h1 {
    color: #ffffff;
    font-size: 24px;
    font-weight: 800;
    margin: 0 0 12px;
    letter-spacing: -0.02em;
    text-align: center;
  }
  h2 {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
    margin: 0 0 12px;
  }
  p {
    line-height: 1.65;
    color: #b4b4c8;
    margin: 10px 0;
    font-size: 15px;
  }
  strong { color: #ffffff; }
  .code {
    background: #0a0a0f;
    border: 2px dashed #7c5cff;
    padding: 24px;
    border-radius: 16px;
    text-align: center;
    font-size: 36px;
    letter-spacing: 10px;
    color: #a78bfa;
    font-weight: 800;
    margin: 24px 0;
    font-family: 'Courier New', monospace;
  }
  .btn {
    display: inline-block;
    background: linear-gradient(135deg, #7c5cff, #4f46e5);
    color: #ffffff !important;
    padding: 18px 36px;
    border-radius: 14px;
    text-decoration: none;
    font-weight: 700;
    font-size: 15px;
    margin: 8px 0;
    letter-spacing: -0.01em;
    box-shadow: 0 8px 32px rgba(124, 92, 255, 0.4);
  }
  .btn-container {
    text-align: center;
    margin: 28px 0;
  }
  .info {
    background: #0a0a0f;
    border-radius: 14px;
    padding: 20px;
    margin: 20px 0;
    border: 1px solid #2a2a3a;
  }
  .info-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    color: #b4b4c8;
    font-size: 14px;
    border-bottom: 1px solid #1c1c28;
  }
  .info-row:last-child { border-bottom: none; }
  .info-label { color: #6b6b80; font-weight: 500; }
  .info-value { color: #ffffff; font-weight: 700; }
  .highlight {
    background: rgba(124, 92, 255, 0.1);
    border: 1px solid rgba(124, 92, 255, 0.3);
    border-radius: 12px;
    padding: 16px;
    margin: 20px 0;
    color: #a78bfa;
    font-size: 14px;
    line-height: 1.55;
  }
  .warning {
    background: rgba(245, 158, 11, 0.08);
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: 12px;
    padding: 16px;
    margin: 20px 0;
    color: #fbbf24;
    font-size: 14px;
    line-height: 1.55;
  }
  .success-icon {
    width: 72px;
    height: 72px;
    border-radius: 50%;
    background: linear-gradient(135deg, #10b981, #059669);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 36px;
    margin: 0 auto 20px;
    box-shadow: 0 0 40px rgba(16, 185, 129, 0.5);
  }
  .footer {
    text-align: center;
    color: #6b6b80;
    font-size: 12px;
    margin-top: 32px;
    line-height: 1.6;
  }
  .footer a {
    color: #7c5cff;
    text-decoration: none;
  }
  .divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #2a2a3a, transparent);
    margin: 24px 0;
  }
  @media (max-width: 480px) {
    .card { padding: 28px 20px; border-radius: 16px; }
    h1 { font-size: 20px; }
    .code { font-size: 28px; letter-spacing: 6px; padding: 18px; }
    .btn { padding: 16px 28px; font-size: 14px; }
  }
</style>
"""


# ============================================
# 📧 TEMPLATE: CÓDIGO DE VERIFICAÇÃO
# ============================================
VERIFICATION_TEMPLATE = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verificação</title>
    {_BASE_STYLE}
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <div class="logo">🔐</div>
            <h1>Código de {{purpose}}</h1>
            <p>Olá! Use o código abaixo para continuar. Ele é válido por <strong>15 minutos</strong>.</p>

            <div class="code">{{code}}</div>

            <div class="warning">
                ⚠️ <strong>Não compartilhe este código com ninguém.</strong><br>
                Se você não solicitou este código, ignore este e-mail.
            </div>

            <div class="footer">
                © {{year}} {{bot_name}}<br>
                Este é um e-mail automático, não responda.
            </div>
        </div>
    </div>
</body>
</html>"""


# ============================================
# 📦 TEMPLATE: ENTREGA DE PRODUTO
# ============================================
PRODUCT_DELIVERY_TEMPLATE = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seu Produto</title>
    {_BASE_STYLE}
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <div class="logo">📦</div>
            <h1>Seu produto está pronto!</h1>

            <p>Olá, <strong>{{user_name}}</strong>! Sua compra foi confirmada e o produto já está disponível.</p>

            <div class="info">
                <div class="info-row">
                    <span class="info-label">Produto</span>
                    <span class="info-value">{{product_name}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Pedido</span>
                    <span class="info-value">{{order_code}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Quantidade</span>
                    <span class="info-value">{{quantity}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Valor</span>
                    <span class="info-value">R$ {{value}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Data da compra</span>
                    <span class="info-value">{{date}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Vencimento</span>
                    <span class="info-value">{{expiration}}</span>
                </div>
            </div>

            <div class="divider"></div>

            <p style="text-align:center;font-size:16px;color:#ffffff;font-weight:600;">
                Para acessar os dados do produto, clique no botão abaixo:
            </p>

            <div class="btn-container">
                <a href="{{activation_url}}" class="btn">🔓 ACESSAR PRODUTO</a>
            </div>

            <div class="highlight">
                🔑 <strong>Importante:</strong> você precisará digitar sua <strong>senha de saque</strong> cadastrada para liberar o produto.
            </div>

            <div class="warning">
                ⚠️ <strong>Este link é pessoal e intransferível.</strong><br>
                Não compartilhe com ninguém. Expira em até 30 dias.
            </div>

            <div class="footer">
                © {{year}} {{bot_name}}<br>
                Este é um e-mail automático, não responda.
            </div>
        </div>
    </div>
</body>
</html>"""


# ============================================
# 🔑 TEMPLATE: RECUPERAÇÃO DE SENHA
# ============================================
RECOVERY_TEMPLATE = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recuperação</title>
    {_BASE_STYLE}
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <div class="logo">🔑</div>
            <h1>Recuperação de senha</h1>

            <p>Recebemos um pedido para redefinir sua senha de saque.</p>

            <p>Use o código abaixo para continuar:</p>

            <div class="code">{{code}}</div>

            <div class="highlight">
                ⏰ Este código é válido por <strong>15 minutos</strong>.
            </div>

            <div class="warning">
                Se não foi você, ignore este e-mail. Sua senha está segura.
            </div>

            <div class="footer">
                © {{year}} {{bot_name}}<br>
                Este é um e-mail automático, não responda.
            </div>
        </div>
    </div>
</body>
</html>"""


# ============================================
# 🧾 TEMPLATE: COMPROVANTE
# ============================================
RECEIPT_TEMPLATE = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comprovante</title>
    {_BASE_STYLE}
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <div class="logo">🧾</div>
            <h1>Comprovante de Compra</h1>

            <p>Olá, <strong>{{user_name}}</strong>! Obrigado pela sua compra.</p>

            <div class="info">
                <div class="info-row">
                    <span class="info-label">Pedido</span>
                    <span class="info-value">{{order_code}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Produto</span>
                    <span class="info-value">{{product_name}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Quantidade</span>
                    <span class="info-value">{{quantity}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Valor</span>
                    <span class="info-value">R$ {{value}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Data</span>
                    <span class="info-value">{{date}}</span>
                </div>
            </div>

            <div class="highlight">
                💡 Guarde este comprovante. Em caso de dúvidas, entre em contato pelo atendimento.
            </div>

            <div class="footer">
                © {{year}} {{bot_name}}<br>
                Este é um e-mail automático, não responda.
            </div>
        </div>
    </div>
</body>
</html>"""


# ============================================
# ✅ TEMPLATE: PAGAMENTO APROVADO
# ============================================
PAYMENT_APPROVED_TEMPLATE = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pagamento Aprovado</title>
    {_BASE_STYLE}
</head>
<body>
    <div class="wrapper">
        <div class="card">
            <div class="success-icon">✓</div>
            <h1>Pagamento aprovado!</h1>

            <p>Olá, <strong>{{user_name}}</strong>! Seu pagamento foi confirmado e o saldo já está disponível.</p>

            <div class="info">
                <div class="info-row">
                    <span class="info-label">Valor</span>
                    <span class="info-value">R$ {{value}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Novo saldo</span>
                    <span class="info-value">R$ {{new_balance}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">ID</span>
                    <span class="info-value">{{payment_id}}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Data</span>
                    <span class="info-value">{{date}}</span>
                </div>
            </div>

            <p style="text-align:center;color:#10b981;font-weight:600;">
                🎉 Aproveite suas compras!
            </p>

            <div class="footer">
                © {{year}} {{bot_name}}<br>
                Este é um e-mail automático, não responda.
            </div>
        </div>
    </div>
</body>
</html>"""


# ============================================
# 🎨 RENDER
# ============================================
def _render_template(template_str: str, variables: dict[str, Any]) -> str:
    """Renderiza template Jinja2."""
    tpl = Template(template_str)
    return tpl.render(**variables)


# ============================================
# 🧪 TESTE DE CONEXÃO
# ============================================
async def test_connection() -> dict[str, Any]:
    """Testa se o SMTP está configurado e acessível."""
    if not settings.smtp_user or not settings.smtp_password:
        return {"ok": False, "error": "SMTP não configurado."}

    try:
        smtp = aiosmtplib.SMTP(
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_use_tls,
            timeout=10,
        )
        await smtp.connect()
        await smtp.login(settings.smtp_user, settings.smtp_password)
        await smtp.quit()
        return {
            "ok": True,
            "host": settings.smtp_host,
            "user": settings.smtp_user,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
