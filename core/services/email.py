# ============================================
# 📧 EMAIL SERVICE — Larizinha Store
# ============================================
# Envio de e-mail via SMTP (assíncrono).
# Templates em HTML com Jinja2.
# Fluxos:
#   - Código de verificação
#   - Entrega de produto com link de ativação
#   - Recuperação de senha de saque
#   - Comprovante de compra
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
) -> dict[str, Any]:
    """
    Envia e-mail via SMTP.
    Retorna dict com sucesso e erro (se houver).
    """
    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("⚠️ SMTP não configurado.")
        return {"success": False, "error": "SMTP não configurado."}

    from_email = settings.smtp_from_email or settings.smtp_user
    from_name = settings.smtp_from_name or "Larizinha Store"

    message = MIMEMultipart("alternative")
    message["From"] = f"{from_name} <{from_email}>"
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
    text = f"Seu código de {purpose} é: {code}\n\nNão compartilhe com ninguém."
    return await send_email(to_email, subject, html, text)


# ============================================
# 📦 ENTREGA DE PRODUTO
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
    O link NÃO é enviado no Telegram.
    """
    # Gera token único para ativar no site
    activation_token = secrets.token_urlsafe(32)

    # Salva o token no pedido (via note/extra na Order ou no User)
    # Aqui usamos o próprio order_code como referência
    activation_url = f"{settings.activation_url}/{order.order_code}?t={activation_token}"

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
        f"Valor: R$ {valor}\n\n"
        f"Para acessar, clique no link abaixo:\n{activation_url}\n\n"
        f"Você precisará digitar sua senha de saque cadastrada."
    )

    result = await send_email(to_email, subject, html, text)

    if result.get("success"):
        logger.info(
            f"📧 Produto entregue por e-mail: pedido {order.order_code} "
            f"→ {to_email}"
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
    text = f"Seu código de recuperação é: {code}\n\nVálido por 15 minutos."
    return await send_email(to_email, subject, html, text)


# ============================================
# 🧾 COMPROVANTE
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

    subject = f"🧾 Comprovante - Pedido {order.order_code}"
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
# 🎨 TEMPLATES HTML
# ============================================
def _render_template(template_str: str, variables: dict[str, Any]) -> str:
    """Renderiza template Jinja2."""
    tpl = Template(template_str)
    return tpl.render(**variables)


_BASE_STYLE = """
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
         background: #0f0f14; margin: 0; padding: 24px; color: #e6e6e6; }
  .card { max-width: 560px; margin: 0 auto; background: #1a1a24;
          border-radius: 16px; padding: 32px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.4);
          border: 1px solid #2a2a38; }
  h1 { color: #ffffff; font-size: 22px; margin: 0 0 12px; }
  p { line-height: 1.6; color: #c8c8d0; margin: 8px 0; }
  .code { background: #0f0f14; border: 1px dashed #7c5cff;
          padding: 18px; border-radius: 12px; text-align: center;
          font-size: 32px; letter-spacing: 6px; color: #a78bfa;
          font-weight: 700; margin: 20px 0; }
  .btn { display: inline-block; background: linear-gradient(135deg,#7c5cff,#4f46e5);
         color: #ffffff !important; padding: 14px 28px; border-radius: 12px;
         text-decoration: none; font-weight: 600; margin: 20px 0; }
  .info { background: #0f0f14; border-radius: 12px; padding: 16px;
          margin: 16px 0; border: 1px solid #2a2a38; }
  .info-row { display: flex; justify-content: space-between;
              padding: 6px 0; color: #c8c8d0; font-size: 14px; }
  .info-label { color: #8b8b99; }
  .info-value { color: #ffffff; font-weight: 600; }
  .footer { text-align: center; color: #6b6b7a; font-size: 12px;
            margin-top: 24px; }
</style>
"""


VERIFICATION_TEMPLATE = (
    f"""<!DOCTYPE html><html><head><meta charset="utf-8">{_BASE_STYLE}</head>
<body><div class="card">
<h1>🔐 Código de {{purpose}}</h1>
<p>Use o código abaixo para continuar. Ele é válido por 15 minutos.</p>
<div class="code">{{code}}</div>
<p>⚠️ <strong>Não compartilhe este código com ninguém.</strong></p>
<p>Se você não solicitou este código, ignore este e-mail.</p>
<div class="footer">© {{year}} {{bot_name}}</div>
</div></body></html>"""
)


PRODUCT_DELIVERY_TEMPLATE = (
    f"""<!DOCTYPE html><html><head><meta charset="utf-8">{_BASE_STYLE}</head>
<body><div class="card">
<h1>📦 Seu produto está pronto!</h1>
<p>Olá, <strong>{{user_name}}</strong>! Sua compra foi confirmada.</p>
<div class="info">
  <div class="info-row"><span class="info-label">Produto</span>
    <span class="info-value">{{product_name}}</span></div>
  <div class="info-row"><span class="info-label">Pedido</span>
    <span class="info-value">{{order_code}}</span></div>
  <div class="info-row"><span class="info-label">Quantidade</span>
    <span class="info-value">{{quantity}}</span></div>
  <div class="info-row"><span class="info-label">Valor</span>
    <span class="info-value">R$ {{value}}</span></div>
  <div class="info-row"><span class="info-label">Data</span>
    <span class="info-value">{{date}}</span></div>
  <div class="info-row"><span class="info-label">Vencimento</span>
    <span class="info-value">{{expiration}}</span></div>
</div>
<p>Para acessar os dados do produto, clique no botão abaixo:</p>
<div style="text-align:center">
  <a href="{{activation_url}}" class="btn">🔓 ACESSAR PRODUTO</a>
</div>
<p>🔑 Você precisará digitar sua <strong>senha de saque</strong> cadastrada
para liberar o produto.</p>
<p>⚠️ Este link é pessoal e intransferível. Não compartilhe.</p>
<div class="footer">© {{year}} {{bot_name}}</div>
</div></body></html>"""
)


RECOVERY_TEMPLATE = (
    f"""<!DOCTYPE html><html><head><meta charset="utf-8">{_BASE_STYLE}</head>
<body><div class="card">
<h1>🔑 Recuperação de senha</h1>
<p>Recebemos um pedido para redefinir sua senha de saque.</p>
<div class="code">{{code}}</div>
<p>Este código é válido por 15 minutos.</p>
<p>Se não foi você, ignore este e-mail. Sua senha está segura.</p>
<div class="footer">© {{year}} {{bot_name}}</div>
</div></body></html>"""
)


RECEIPT_TEMPLATE = (
    f"""<!DOCTYPE html><html><head><meta charset="utf-8">{_BASE_STYLE}</head>
<body><div class="card">
<h1>🧾 Comprovante de Compra</h1>
<p>Olá, <strong>{{user_name}}</strong>! Obrigado pela compra.</p>
<div class="info">
  <div class="info-row"><span class="info-label">Pedido</span>
    <span class="info-value">{{order_code}}</span></div>
  <div class="info-row"><span class="info-label">Produto</span>
    <span class="info-value">{{product_name}}</span></div>
  <div class="info-row"><span class="info-label">Quantidade</span>
    <span class="info-value">{{quantity}}</span></div>
  <div class="info-row"><span class="info-label">Valor</span>
    <span class="info-value">R$ {{value}}</span></div>
  <div class="info-row"><span class="info-label">Data</span>
    <span class="info-value">{{date}}</span></div>
</div>
<p>Guarde este comprovante. Em caso de dúvidas, entre em contato
pelo atendimento.</p>
<div class="footer">© {{year}} {{bot_name}}</div>
</div></body></html>"""
)


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
        return {"ok": True, "host": settings.smtp_host}
    except Exception as e:
        return {"ok": False, "error": str(e)}
