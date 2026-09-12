# ============================================
# 🌐 STATIC ROUTES — Larizinha Store
# ============================================
# Serve os arquivos estáticos do WebApp.
#
# Responsabilidades:
#   - Servir /webapp → index.html
#   - Servir /webapp/static/* → CSS, JS, imagens
#   - Servir /webapp/activate/* → página de ativação
#
# Todas as rotas apontam pra pasta webapp/ na raiz
# do projeto. FastAPI serve os arquivos direto.
# ============================================

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from loguru import logger


router = APIRouter(prefix="/webapp", tags=["webapp-static"])


# ============================================
# 📁 CAMINHOS
# ============================================
# Pasta raiz do projeto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
WEBAPP_DIR = BASE_DIR / "webapp"
STATIC_DIR = WEBAPP_DIR / "static"


def _safe_file(base: Path, filename: str) -> Path:
    """
    Retorna o caminho absoluto do arquivo,
    garantindo que não sai da pasta base (path traversal).
    """
    # Remove tentativas de traversal
    filename = filename.replace("..", "").lstrip("/")

    target = (base / filename).resolve()
    base_resolved = base.resolve()

    # Verifica se está dentro da pasta base
    try:
        target.relative_to(base_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return target


# ============================================
# 🏠 INDEX (Mini App)
# ============================================
@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def webapp_index():
    """Serve o index.html do Mini App."""
    index_path = WEBAPP_DIR / "index.html"

    if not index_path.exists():
        logger.error(f"❌ index.html não encontrado em {index_path}")
        raise HTTPException(
            status_code=404,
            detail="Mini App não configurado",
        )

    return FileResponse(
        index_path,
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Frame-Options": "ALLOWALL",  # Telegram WebApp precisa
        },
    )


# ============================================
# 📄 PÁGINA DE ATIVAÇÃO
# ============================================
@router.get("/activate", include_in_schema=False)
@router.get("/activate/", include_in_schema=False)
@router.get("/activate/{token}", include_in_schema=False)
async def webapp_activate(token: str = ""):
    """
    Serve a página de ativação.
    O token vem do e-mail enviado ao cliente.
    """
    activate_path = WEBAPP_DIR / "activate.html"

    if not activate_path.exists():
        logger.error(f"❌ activate.html não encontrado em {activate_path}")
        raise HTTPException(
            status_code=404,
            detail="Página de ativação não configurada",
        )

    return FileResponse(
        activate_path,
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Frame-Options": "ALLOWALL",
        },
    )


# ============================================
# 🎨 ARQUIVOS ESTÁTICOS (CSS, JS, imagens)
# ============================================
@router.get("/static/{filepath:path}", include_in_schema=False)
async def webapp_static(filepath: str):
    """
    Serve arquivos estáticos da pasta webapp/static/.
    Exemplos:
      /webapp/static/style.css
      /webapp/static/app.js
      /webapp/static/img/logo.png
    """
    target = _safe_file(STATIC_DIR, filepath)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    # Detecta o media type
    suffix = target.suffix.lower()
    media_types = {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".mjs": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".txt": "text/plain; charset=utf-8",
        ".map": "application/json",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    # Cache longo pra arquivos estáticos com versão
    # (querystring ?v=123 no HTML força atualização)
    cache_control = (
        "public, max-age=3600"
        if suffix in (".css", ".js", ".png", ".jpg", ".jpeg",
                      ".gif", ".webp", ".svg", ".ico", ".woff",
                      ".woff2", ".ttf", ".otf")
        else "no-cache"
    )

    return FileResponse(
        target,
        media_type=media_type,
        headers={"Cache-Control": cache_control},
    )


# ============================================
# 🖼️ IMAGENS DO WEBAPP (opcional)
# ============================================
@router.get("/img/{filepath:path}", include_in_schema=False)
async def webapp_img(filepath: str):
    """Serve imagens da pasta webapp/img/."""
    img_dir = WEBAPP_DIR / "img"
    target = _safe_file(img_dir, filepath)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    suffix = target.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }

    return FileResponse(
        target,
        media_type=media_types.get(suffix, "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ============================================
# 🏥 HEALTHCHECK DO WEBAPP
# ============================================
@router.get("/health", include_in_schema=False)
async def webapp_health():
    """Verifica se os arquivos do WebApp existem."""
    return {
        "ok": True,
        "index_exists": (WEBAPP_DIR / "index.html").exists(),
        "activate_exists": (WEBAPP_DIR / "activate.html").exists(),
        "css_exists": (STATIC_DIR / "style.css").exists(),
        "js_exists": (STATIC_DIR / "app.js").exists(),
    }


# ============================================
# 📌 FALLBACK (para SPA — redireciona 404 pro index)
# ============================================
@router.get("/{path:path}", include_in_schema=False)
async def webapp_spa_fallback(path: str):
    """
    Se o cliente acessar qualquer rota do /webapp/* que não existe,
    serve o index.html (SPA-style).
    """
    # Se é um arquivo real, serve
    target = _safe_file(WEBAPP_DIR, path)
    if target.exists() and target.is_file():
        suffix = target.suffix.lower()
        if suffix in (".css", ".js", ".png", ".jpg", ".jpeg",
                      ".gif", ".webp", ".svg", ".ico", ".woff",
                      ".woff2", ".ttf", ".otf"):
            # Serve como estático
            return await webapp_static(path)

    # Senão, serve o index
    index_path = WEBAPP_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Não encontrado")

    return FileResponse(
        index_path,
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )
