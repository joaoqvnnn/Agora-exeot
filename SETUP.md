# 🛠️ SETUP — Plataforma Larizinha Store

Guia de preparação do ambiente. Siga na ordem. Não pule etapas.

---

## 🧱 Stack do projeto

| Camada | Tecnologia | Por quê |
|---|---|---|
| Bot Telegram | Python + aiogram 3 | Webhook (funciona no Render grátis) |
| API/Webhook | FastAPI + Uvicorn | Recebe Telegram, Mercado Pago, WhatsApp |
| Banco | PostgreSQL (Neon.tech) | Grátis pra sempre |
| ORM | SQLAlchemy 2.0 | Modelos e consultas |
| Migrations | Alembic | Alterar tabelas sem perder dados |
| Agendador | APScheduler (in-process) | Sem Redis (Render grátis não tem) |
| Mini App / Web | Next.js (fase futura) | Loja + ativação |
| Hospedagem | Render | Grátis com webhook |

---

## 📦 PASSO 1 — Criar conta no Neon.tech (banco grátis)

1. Acesse: https://neon.tech
2. Clica em **Sign Up**
3. Escolhe **"Continue with GitHub"** (usa a mesma conta do GitHub)
4. Autoriza
5. Clica em **Create Project**
   - **Name:** `larizinha-store`
   - **Region:** `AWS South America (São Paulo)` — importante pra ficar rápido no Brasil
   - **Postgres version:** deixa a padrão
6. Depois de criar, ele mostra uma **Connection String**. Vai ser assim:
