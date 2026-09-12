# ============================================
# 🗄️ MIGRATIONS/ENV.PY — Larizinha Store
# ============================================
# O "cérebro" do Alembic.
#
# ✨ CORRIGIDO:
#   - Adiciona a RAIZ DO PROJETO no sys.path
#   - Isso resolve o "ModuleNotFoundError: No module named 'core'"
#   - Funciona local E no Render
#
# Responsabilidades:
#   1. Adicionar raiz do projeto no sys.path
#   2. Ler a URL do banco do core.config
#   3. Importar TODOS os models
#   4. Configurar modo offline e online
#   5. Suportar async (asyncpg)
# ============================================

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config


# ============================================
# 🔧 CORREÇÃO CRÍTICA — Adiciona raiz no sys.path
# ============================================
# Sem isso, o Alembic não encontra a pasta `core`.
#
# Como funciona:
#   __file__ → .../migrations/env.py
#   .parent  → .../migrations/
#   .parent  → .../  (raiz do projeto)
#
# Aí adicionamos essa raiz no sys.path pra o Python
# conseguir importar `from core.config import settings`.
# ============================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================
# 📥 IMPORTAÇÕES DO PROJETO
# ============================================
# Estas importações são CRÍTICAS.
# Sem elas, o Alembic não enxerga os models.

# 1. Configurações (lê .env / Render)
from core.config import settings

# 2. Base (classe-mãe dos models)
from core.database import Base

# 3. TODOS os models (importa o pacote inteiro)
from core import models  # noqa: F401


# ============================================
# ⚙️ CONFIGURAÇÃO DO ALEMBIC
# ============================================
config = context.config

# Sobrescreve a URL do banco com a do .env/Render.
config.set_main_option("sqlalchemy.url", settings.database_url_async)

# Configura logging (lê a seção [loggers] do alembic.ini)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ============================================
# 📋 METADATA DOS MODELS
# ============================================
target_metadata = Base.metadata


# ============================================
# 🚫 TABELAS IGNORADAS
# ============================================
EXCLUDE_TABLES: set[str] = set()


# ============================================
# 🧪 FILTROS AUXILIARES
# ============================================
def include_object(
    obj,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to,
) -> bool:
    """Filtro de objetos que o Alembic deve considerar."""
    if type_ == "table" and name in EXCLUDE_TABLES:
        return False

    if type_ == "table" and name and name.startswith("pg_"):
        return False

    return True


def process_revision_directives(
    context,
    revision,
    directives,
) -> None:
    """Hook chamado antes de escrever o arquivo de migration."""
    if getattr(context.config.cmd_opts, "autogenerate", False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            print("ℹ️  Nenhuma mudança detectada. Migration vazia ignorada.")


# ============================================
# 🔌 MODO OFFLINE
# ============================================
def run_migrations_offline() -> None:
    """Roda migrations no modo 'offline' (só gera SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================
# 🔌 MODO ONLINE (síncrono)
# ============================================
def do_run_migrations(connection: Connection) -> None:
    """Executa as migrations numa conexão já aberta."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
        process_revision_directives=process_revision_directives,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================
# 🔌 MODO ONLINE (assíncrono)
# ============================================
async def run_async_migrations() -> None:
    """Roda migrations no modo 'online' (assíncrono)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entrypoint do modo online (chama a versão async)."""
    asyncio.run(run_async_migrations())


# ============================================
# 🚀 ENTRYPOINT
# ============================================
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
