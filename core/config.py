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
    # 📱 WHATSAPP (não oficial)
    # --------------------------------------------
    whatsapp_api_url: Optional[str] = None
    whatsapp_api_key: Optional[str] = None
    whatsapp_phone_number: Optional[str] = None

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
    base_url: str = "https://seu-servico.onrender.com"
    webapp_url: str = "https://seu-servico.onrender.com/webapp"
    activation_url: str = "https://seu-servico.onrender.com/ativar"

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
    from rich import print as rprint  # opcional

    rprint("[bold green]✅ Configurações carregadas:[/bold green]")
    rprint(f"Ambiente: {settings.environment}")
    rprint(f"Produção? {settings.is_production}")
    rprint(f"Webhook bot: {settings.telegram_webhook_full_url}")
    rprint(f"Banco (async): {settings.database_url_async[:60]}...")

# ============================================
# FIM
# ============================================
