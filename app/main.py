"""Entrypoint principal FastAPI da Plataforma Concurso 2027."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import APP_TITLE, BASE_DIR, LOGS_DIR
from app.database import Base, SessionLocal, engine
from app.routers.web_router import router as web_router
from app.services.seed_service import inicializar_dados_plataforma

# Configuração de logs rotativos locais em data/logs/app.log
log_file = LOGS_DIR / "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(
            str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("plataforma2027")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa esquema SQLite e indexa/semeia o acervo documental de forma idempotente."""
    logger.info("Inicializando Plataforma Concurso 2027...")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        stats = inicializar_dados_plataforma(db)
        logger.info(
            "Acervo e Matriz Integrada verificados: %s arquivos em disco.",
            stats.get("total_arquivos_disco", 0),
        )
    yield
    logger.info("Encerrando Plataforma Concurso 2027.")


app = FastAPI(
    title=APP_TITLE,
    version="1.0.0",
    description="Plataforma Inteligente de Preparação para Concursos 2027 — SEFAZ-PE (60%) e ANPD + Dados & TI (40%)",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "app" / "static")),
    name="static",
)

app.include_router(web_router)
