# ============================================
# 🗄️ MIGRATIONS/ENV.PY — Larizinha Store
# ============================================
# O "cérebro" do Alembic.
#
# Responsabilidades:
#   1. Ler a URL do banco do core.config (não do .ini)
#   2. Importar TODOS os models (pra o Alembic enxergar)
#   3. Configurar modo offline (gera SQL sem conectar)
#   4. Configurar modo online (conecta e aplica)
#   5. Suportar async (asyncpg) e sync (psycopg2)
#
# ⚠️ IMPORTANTE:
#   Se você criar um model novo em core/models.py,
#   o import abaixo ("from core import models")
#   já cobre ele automaticamente. Só não esqueça de
#   rodar "alembic revision --autogenerate" depois.
# ============================================

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ============================================
# 📥 IMPORTAÇÕES DO PROJETO
# ============================================
# Estas importações são CRÍTICAS.
# Sem elas, o Alembic não enxerga os models
# e não gera as migrations corretamente.

# 1. Configurações (lê .env / Render)
from core.config import settings

# 2. Base (classe-mãe dos models)
from core.database import Base

# 3. TODOS os models (importa o pacote inteiro)
#    Isso faz o Python executar core/models.py
#    e registrar todas as tabelas na Base.metadata.
from core import models  # noqa: F401


# ============================================
# ⚙️ CONFIGURAÇÃO DO ALEMBIC
# ============================================
# Pega a configuração do arquivo alembic.ini
config = context.config

# Sobrescreve a URL do banco com a do .env/Render.
# Isso evita colocar credenciais no alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database_url_async)

# Configura logging (lê a seção [loggers] do alembic.ini)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ============================================
# 📋 METADATA DOS MODELS
# ============================================
# O Alembic usa isso pra comparar o estado atual
# do banco com o estado dos models, e gerar
# as migrations necessárias.
target_metadata = Base.metadata


# ============================================
# 🚫 TABELAS IGNORADAS
# ============================================
# Se houver tabelas que NÃO queremos versionar
# (ex: tabelas internas do Postgres), listamos aqui.
#
# Por enquanto, nenhuma. Todas as tabelas são nossas.
# ============================================
EXCLUDE_TABLES: set[str] = set()


# ============================================
# 🧪 FUNÇÕES AUXILIARES
# ============================================

def include_object(
    obj,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to,
) -> bool:
    """
    Filtro de objetos que o Alembic deve considerar.

    Retorna True → inclui na migration
    Retorna False → ignora

    Usos comuns:
        - Ignorar tabelas específicas
        - Ignorar índices temporários
        - Ignorar views
    """
    # Ignora tabelas na lista de exclusão
    if type_ == "table" and name in EXCLUDE_TABLES:
        return False

    # Ignora tabelas do sistema Postgres
    if type_ == "table" and name and name.startswith("pg_"):
        return False

    return True


def process_revision_directives(
    context,
    revision,
    directives,
) -> None:
    """
    Hook chamado antes de escrever o arquivo de migration.

    Usos:
        - Bloquear migration vazia (sem mudanças)
        - Adicionar comentários automáticos
        - Formatar SQL gerado

    Aqui: bloqueia migrations vazias automaticamente.
    """
    # Se a migration não tem mudanças, avisa e aborta
    if getattr(context.config.cmd_opts, "autogenerate", False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            print("ℹ️  Nenhuma mudança detectada. Migration vazia ignorada.")


# ============================================
# 🔌 MODO OFFLINE
# ============================================
# Gera o SQL das migrations SEM conectar no banco.
# Útil pra revisar o que vai ser aplicado antes
# de aplicar de verdade.
#
# Uso:
#   alembic upgrade head --sql > migration.sql
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
# 🔌 MODO ONLINE — SINCRONO (fallback)
# ============================================
# Conecta no banco de forma síncrona (psycopg2).
# Usado quando asyncpg não está disponível.
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
        # Importante pra detectar mudanças em ENUMs
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Roda migrations no modo 'online' (conecta no banco).
    Versão assíncrona — usa asyncpg.
    """
    # Cria engine assíncrono com a URL do banco
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        # Passa a conexão assíncrona pro contexto do Alembic
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entrypoint do modo online (chama a versão async)."""
    asyncio.run(run_async_migrations())


# ============================================
# 🚀 ENTRYPOINT
# ============================================
# Decide qual modo rodar baseado no contexto.
# Normalmente, o Alembic chama isso automaticamente.
# ============================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()


# ============================================
# 📌 OBSERVAÇÕES IMPORTANTES
# ============================================
# 1. Este arquivo LÊ a URL do banco do .env/Render.
#    NUNCA coloque credenciais aqui.
#
# 2. Se você criar uma tabela nova em core/models.py,
#    o import "from core import models" já cobre.
#    Só rode:
#       alembic revision --autogenerate -m "add tabela X"
#       alembic upgrade head
#
# 3. Se o Alembic reclamar de ENUMs duplicados,
#    é porque o Postgres não sobrescreve ENUM.
#    Nesse caso, crie o ENUM manualmente com
#    "CREATE TYPE ... IF NOT EXISTS".
#
# 4. compare_type=True → detecta mudança de tipo
#    compare_server_default=True → detecta mudança de default
#    Ambos evitam que o Alembic "ignore" mudanças sutis.
#
# 5. NUNCA edite uma migration já aplicada em produção.
#    Crie uma nova pra corrigir.
# ============================================

# ============================================
# FIM
# ============================================
