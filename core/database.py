# ============================================
# 🗄️ DATABASE — Larizinha Store
# ============================================
# Conexão assíncrona com o banco PostgreSQL (Neon).
#
# O que este arquivo faz:
#   1. Cria o engine (motor de conexão)
#   2. Cria a SessionLocal (fábrica de sessões)
#   3. Define a Base (classe-mãe dos models)
#   4. Oferece gerenciador de contexto pra sessões
#   5. Oferece healthcheck pra testar conexão
#
# Como usar:
#   async with get_session() as session:
#       user = await session.get(User, user_id)
#
# ⚠️ NUNCA use "create_all" em produção quando o Alembic
# estiver ativo. Use migrations.
# ============================================

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import settings


# ============================================
# 🧱 BASE DOS MODELS
# ============================================
class Base(DeclarativeBase):
    """
    Classe-mãe de TODOS os models (tabelas).

    Cada model vai herdar dela:
        class User(Base):
            __tablename__ = "users"
            ...

    O SQLAlchemy usa essa classe pra mapear
    Python ↔ PostgreSQL automaticamente.
    """
    pass


# ============================================
# 🔌 ENGINE ASSÍNCRONO
# ============================================
# O engine é o "motor" que mantém o pool de conexões.
# Ele é criado UMA vez e reutilizado em todo o sistema.
#
# Configurações importantes:
#   - pool_pre_ping: testa a conexão antes de usar (evita "conexão morta")
#   - pool_recycle: recicla conexões a cada 5 min (Neon fecha conexões ociosas)
#   - echo: imprime SQL no console (só em desenvolvimento)
# ============================================

engine = create_async_engine(
    settings.database_url_async,
    echo=settings.is_development,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    pool_timeout=30,
    future=True,
)


# ============================================
# 🏭 FÁBRICA DE SESSÕES
# ============================================
# Cada operação no banco cria uma "sessão" temporária.
# A fábrica abaixo produz essas sessões.
#
# Configurações:
#   - expire_on_commit=False: objetos continuam válidos após commit
#   - autoflush=False: controlamos manualmente quando salvar
# ============================================

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ============================================
# 🔄 GERENCIADOR DE CONTEXTO (uso recomendado)
# ============================================
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Gerenciador de contexto pra usar sessão do banco.

    Uso:
        async with get_session() as session:
            user = await session.get(User, 123)
            user.balance = 10
            await session.commit()

    Vantagens:
        - Abre e fecha a sessão automaticamente
        - Se der erro, faz rollback automático
        - Não vaza conexão

    Equivale ao "try/finally" com commit/rollback manual.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Erro na sessão do banco: {e}")
        raise
    finally:
        await session.close()


# ============================================
# 🔄 DEPENDÊNCIA FASTAPI (uso em endpoints)
# ============================================
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependência FastAPI pra injetar sessão do banco.

    Uso em endpoints:
        @app.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db)):
            ...

    O FastAPI abre a sessão, injeta no endpoint,
    e fecha automaticamente ao terminar a requisição.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ============================================
# 🏥 HEALTHCHECK
# ============================================
async def check_database_connection() -> bool:
    """
    Testa se o banco está respondendo.

    Uso:
        if await check_database_connection():
            print("Banco OK")

    Retorna True se conectou, False se falhou.
    Útil pra painel de diagnóstico do admin.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            if value == 1:
                logger.info("✅ Banco de dados: conectado")
                return True
            logger.warning("⚠️ Banco respondeu, mas com valor inesperado")
            return False
    except Exception as e:
        logger.error(f"❌ Falha ao conectar no banco: {e}")
        return False


# ============================================
# 📊 INFO DO BANCO (versão, tamanho, etc)
# ============================================
async def get_database_info() -> dict:
    """
    Retorna informações úteis do banco pra diagnóstico.

    Uso:
        info = await get_database_info()
        print(info["version"])
    """
    info = {
        "connected": False,
        "version": None,
        "database": None,
        "user": None,
        "size": None,
    }
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT version()"))
            info["version"] = result.scalar()

            result = await session.execute(text("SELECT current_database()"))
            info["database"] = result.scalar()

            result = await session.execute(text("SELECT current_user"))
            info["user"] = result.scalar()

            result = await session.execute(
                text("SELECT pg_size_pretty(pg_database_size(current_database()))")
            )
            info["size"] = result.scalar()

            info["connected"] = True
            return info
    except Exception as e:
        logger.error(f"❌ Erro ao obter info do banco: {e}")
        return info


# ============================================
# 🔌 GERENCIAMENTO DE CICLO DE VIDA
# ============================================
async def init_database() -> None:
    """
    Chamado na inicialização do sistema (startup).
    Verifica se o banco está acessível.

    Uso:
        @app.on_event("startup")
        async def startup():
            await init_database()
    """
    logger.info("🔄 Inicializando conexão com o banco...")
    ok = await check_database_connection()
    if not ok:
        logger.error("❌ Não foi possível conectar ao banco. Verifique DATABASE_URL.")
        raise RuntimeError("Falha na conexão com o banco de dados.")
    info = await get_database_info()
    logger.info(f"📊 Banco: {info['database']} | Usuário: {info['user']} | Tamanho: {info['size']}")


async def close_database() -> None:
    """
    Chamado no encerramento do sistema (shutdown).
    Fecha o pool de conexões pra liberar recursos.

    Uso:
        @app.on_event("shutdown")
        async def shutdown():
            await close_database()
    """
    logger.info("🔒 Fechando conexões com o banco...")
    await engine.dispose()
    logger.info("✅ Conexões encerradas.")


# ============================================
# 🧪 TESTE RÁPIDO (só roda se executar direto)
# ============================================
if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        logger.info("🧪 Testando conexão com o banco...")
        ok = await check_database_connection()
        if ok:
            info = await get_database_info()
            logger.success(f"✅ Conectado! Versão: {info['version'][:60]}...")
        else:
            logger.error("❌ Falha na conexão.")
        await close_database()

    asyncio.run(main())

# ============================================
# FIM
# ============================================
