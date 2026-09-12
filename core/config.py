# ============================================
# ⚙️ CONFIG — Larizinha Store
# ============================================
# Lê todas as variáveis do .env (ou do painel do Render)
# e disponibiliza pro resto do sistema via:
#
#   from core.config import settings
#   print(settings.telegram_bot_token)
#
# Se alguma variável obrigatória estiver faltando,
# o sistema avisa NA HORA em vez de quebrar depois.
#
# ✨ ATUALIZADO:
#   - Adiciona WhatsApp (Baileys)
#   - Adiciona Activation URL
#   - Adiciona WA Flow settings
# ============================================

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configurações centrais da aplicação.

    Os nomes dos atributos são em snake_case (Python),
    e o Pydantic converte automaticamente para UPPER_CASE
    ao ler do .env (ex: telegram_bot_token lê TELEGRAM_BOT_TOKEN).
    """

    # --------------------------------------------
    # 🚀 AMBIENTE
    # --------------------------------------------
    environment: Literal["development", "production"] = "production"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    timezone: str = "America/Sao_Paulo"

    # --------------------------------------------
    # 🗄️ BANCO DE DADOS
    # --------------------------------------------
    database_url: str = Field(
        ...,
        description="Connection string do Neon.tech (PostgreSQL).",
    )

    # --------------------------------------------
    # 🤖 BOT TELEGRAM — CLIENTE
    # --------------------------------------------
    telegram_bot_token: str = Field(
        ...,
        description="Token do bot cliente (BotFather).",
    )
    telegram_bot_username: str = "meu_bot_cliente"
    telegram_owner_id: int = Field(
        ...,
        description="ID do dono (admin principal).",
    )
    telegram_webhook_url: str = "https://seu-servico.onrender.com"
    telegram_webhook_secret: str = "troque_por_string_aleatoria_longa"

    # --------------------------------------------
    # 🤖 BOT TELEGRAM — ADMIN
    # --------------------------------------------
    telegram_admin_bot_token: Optional[str] = None
    telegram_admin_bot_username: str = "meu_bot_admin"
    telegram_admin_webhook_url: str = "https://seu-servico-admin.onrender.com"
    telegram_admin_webhook_secret: str = "troque_por_outra_string"

    # --------------------------------------------
    # 📢 CANAL OBRIGATÓRIO
    # --------------------------------------------
    telegram_required_channel_id: Optional[int] = None
    telegram_required_channel_link: Optional[str] = None

    # --------------------------------------------
    # 💳 MERCADO PAGO
    # --------------------------------------------
    mercadopago_access_token: str = Field(
        ...,
        description="Access Token de produção do Mercado Pago.",
    )
    mercadopago_public_key: Optional[str] = None
    mercadopago_webhook_secret: Optional[str] = None
    mercadopago_webhook_url: str = "https://seu-servico.onrender.com/webhooks/mercadopago"

    # --------------------------------------------
    # 📧 E-MAIL
    # --------------------------------------------
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_name: str = "Larizinha Store"
    smtp_from_email: Optional[str] = None
    smtp_use_tls: bool = True

    # --------------------------------------------
    # 🤖 OPENAI
    # --------------------------------------------
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 500
    openai_temperature: float = 0.7

    # --------------------------------------------
    # 📱 WHATSAPP (Baileys — serviço Node.js)
    # --------------------------------------------
    whatsapp_api_url: Optional[str] = Field(
        None,
        description="URL do serviço Baileys (ex: https://larizinha-whatsapp.onrender.com)",
    )
    whatsapp_api_key: Optional[str] = Field(
        None,
        description="API key que o Baileys espera (X-Api-Key)",
    )
    whatsapp_phone_number: Optional[str] = Field(
        None,
        description="Número do WhatsApp (formato internacional: 5511999999999)",
    )
    whatsapp_webhook_secret: Optional[str] = Field(
        None,
        description="Secret usado pra validar webhooks do Baileys",
    )

    # --------------------------------------------
    # 🔐 SEGURANÇA / SESSÃO
    # --------------------------------------------
    secret_key: str = Field(
        ...,
        min_length=32,
        description="Chave secreta para JWT. Mínimo 32 caracteres.",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # --------------------------------------------
    # 🛡️ ANTI-FLOOD
    # --------------------------------------------
    antiflood_max_messages: int = 20
    antiflood_window_seconds: int = 10
    antiflood_block_seconds: int = 600

    # --------------------------------------------
    # 🌐 URLS DO SISTEMA
    # --------------------------------------------
    base_url: str = Field(
        "https://seu-servico.onrender.com",
        description="URL base do sistema (sem barra no final)",
    )
    webapp_url: str = Field(
        "https://seu-servico.onrender.com/webapp",
        description="URL do Mini App (loja)",
    )
    activation_url: str = Field(
        "https://seu-servico.onrender.com/webapp/activate",
        description="URL do site de ativação por e-mail",
    )

    # --------------------------------------------
    # 📲 WHATSAPP FLOW (ativação via link)
    # --------------------------------------------
    wa_flow_require_password: bool = Field(
        True,
        description="Exigir senha de saque pra ativar via WhatsApp",
    )
    wa_flow_show_link_direct: bool = Field(
        True,
        description="Enviar link direto no WhatsApp (ou só avisar)",
    )
    wa_flow_link_days: int = Field(
        30,
        description="Dias que o link de ativação do WhatsApp fica válido",
    )
    wa_flow_max_attempts: int = Field(
        5,
        description="Tentativas de senha na ativação via WhatsApp",
    )
    wa_flow_lockout_minutes: int = Field(
        30,
        description="Minutos de bloqueio após exceder tentativas",
    )

    # --------------------------------------------
    # 📊 LOGS / SUPORTE
    # --------------------------------------------
    logs_channel_id: Optional[int] = None
    support_link: str = "https://wa.me/5511999999999"

    # --------------------------------------------
    # ⚙️ CONFIGURAÇÃO DO PYDANTIC
    # --------------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --------------------------------------------
    # ✅ VALIDADORES
    # --------------------------------------------
    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Garante que a connection string é válida."""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError(
                "DATABASE_URL deve começar com 'postgresql://' ou "
                "'postgresql+asyncpg://'"
            )
        return v

    @field_validator("telegram_bot_token")
    @classmethod
    def validate_telegram_token(cls, v: str) -> str:
        """Formato esperado: 123456:ABC-DEF..."""
        if ":" not in v or len(v) < 20:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN inválido. Formato esperado: "
                "'123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ'"
            )
        return v

    @field_validator("openai_temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Temperatura deve ficar entre 0 e 2."""
        if not 0 <= v <= 2:
            raise ValueError("OPENAI_TEMPERATURE deve estar entre 0 e 2.")
        return v

    @field_validator("base_url", "webapp_url", "activation_url", "whatsapp_api_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Garante que URLs terminam sem barra."""
        if v and isinstance(v, str) and v.endswith("/"):
            return v[:-1]
        return v

    @field_validator("whatsapp_phone_number")
    @classmethod
    def validate_whatsapp_phone(cls, v: Optional[str]) -> Optional[str]:
        """Remove tudo que não é dígito do número do WhatsApp."""
        if not v:
            return None
        import re
        return re.sub(r"\D", "", v)

    # --------------------------------------------
    # 🧠 PROPRIEDADES ÚTEIS
    # --------------------------------------------
    @property
    def is_production(self) -> bool:
        """True se estiver rodando em produção."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """True se estiver em desenvolvimento."""
        return self.environment == "development"

    @property
    def database_url_async(self) -> str:
        """
        Retorna a URL formatada para uso com asyncpg (SQLAlchemy async).
        Converte 'postgresql://' para 'postgresql+asyncpg://'.
        """
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def database_url_sync(self) -> str:
        """
        Retorna a URL formatada para uso síncrono (Alembic migrations).
        Converte 'postgresql+asyncpg://' para 'postgresql://'.
        """
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return url

    @property
    def telegram_webhook_full_url(self) -> str:
        """URL completa do webhook do bot cliente."""
        base = self.telegram_webhook_url.rstrip("/")
        return f"{base}/webhook/telegram/{self.telegram_webhook_secret}"

    @property
    def telegram_admin_webhook_full_url(self) -> str:
        """URL completa do webhook do bot admin."""
        base = self.telegram_admin_webhook_url.rstrip("/")
        return f"{base}/webhook/telegram-admin/{self.telegram_admin_webhook_secret}"

    @property
    def whatsapp_api_url_clean(self) -> Optional[str]:
        """URL do Baileys sem barra final."""
        if not self.whatsapp_api_url:
            return None
        return self.whatsapp_api_url.rstrip("/")

    @property
    def wa_flow_enabled(self) -> bool:
        """Verifica se o WhatsApp Flow está configurado."""
        return bool(self.whatsapp_api_url and self.whatsapp_api_key)

    @property
    def has_whatsapp(self) -> bool:
        """Verifica se o WhatsApp está configurado."""
        return bool(self.whatsapp_api_url)

    @property
    def has_email(self) -> bool:
        """Verifica se o SMTP está configurado."""
        return bool(self.smtp_user and self.smtp_password)

    @property
    def has_openai(self) -> bool:
        """Verifica se a OpenAI está configurada."""
        return bool(self.openai_api_key)

    @property
    def has_mercadopago(self) -> bool:
        """Verifica se o Mercado Pago está configurado."""
        return bool(self.mercadopago_access_token)

    @property
    def qr_url(self) -> Optional[str]:
        """URL pública da página do QR Code do WhatsApp."""
        if not self.whatsapp_api_url:
            return None
        return f"{self.whatsapp_api_url_clean}/qr"


# ============================================
# 🔁 SINGLETON — instância única de settings
# ============================================
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Retorna a instância única de Settings.
    O @lru_cache garante que o .env só é lido UMA vez.
    """
    return Settings()


# Atalho global para importar direto:
#   from core.config import settings
settings = get_settings()


# ============================================
# 🧪 TESTE RÁPIDO (só roda se executar este arquivo direto)
# ============================================
if __name__ == "__main__":
    print("✅ Configurações carregadas:")
    print(f"Ambiente: {settings.environment}")
    print(f"Produção? {settings.is_production}")
    print(f"Webhook bot: {settings.telegram_webhook_full_url}")
    print(f"Banco (async): {settings.database_url_async[:60]}...")
    print(f"")
    print(f"📊 Integrações:")
    print(f"├ WhatsApp: {'🟢' if settings.has_whatsapp else '🔴'}")
    print(f"├ E-mail:   {'🟢' if settings.has_email else '🔴'}")
    print(f"├ OpenAI:   {'🟢' if settings.has_openai else '🔴'}")
    print(f"├ Mercado Pago: {'🟢' if settings.has_mercadopago else '🔴'}")
    print(f"└ WA Flow:  {'🟢' if settings.wa_flow_enabled else '🔴'}")
    print(f"")
    print(f"🌐 URLs:")
    print(f"├ Base:       {settings.base_url}")
    print(f"├ WebApp:     {settings.webapp_url}")
    print(f"├ Ativação:   {settings.activation_url}")
    print(f"└ QR:         {settings.qr_url or '—'}")

# ============================================
# FIM
# ============================================
