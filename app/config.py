"""Configurações centrais e caminhos da Plataforma Concurso 2027."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = BASE_DIR / "data"
LOGS_DIR: Path = DATA_DIR / "logs"
EXPORTS_DIR: Path = DATA_DIR / "exports"
BACKUPS_DIR: Path = BASE_DIR / "backups"

# Garantir que os diretórios de dados e backups existam sem tocar no acervo
for _d in (DATA_DIR, LOGS_DIR, EXPORTS_DIR, BACKUPS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

#As 6 pastas oficiais do acervo documental (somente leitura)
ACERVO_FOLDERS: tuple[str, ...] = (
    "01_EDITAIS_E_PLANEJAMENTO",
    "02_SEFAZ_PE",
    "03_ANPD",
    "04_DISCIPLINAS_E_LEGISLACAO",
    "05_PROVAS_E_GABARITOS",
    "06_MATERIAIS_E_INVENTARIO",
)

INVENTARIO_CSV_PATH: Path = (
    BASE_DIR / "06_MATERIAIS_E_INVENTARIO" / "INVENTARIO_GERAL_CONCURSO_2027.csv"
)

APP_TITLE: str = os.getenv("APP_TITLE", "Plataforma Concurso 2027")
APP_HOST: str = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))

DEFAULT_DB_PATH: Path = DATA_DIR / "plataforma2027.sqlite3"
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
)

# Fase inicial: base SEFAZ-PE primeiro, ANPD em cadência leve.
PESO_EIXO_SEFAZ_PE: int = 80
PESO_EIXO_ANPD_TI: int = 20

# Distribuição interna da frente tecnológica (dentro dos 40% do Eixo 2)
DISTRIBUICAO_INTERNA_TECNOLOGIA: dict[str, int] = {
    "Ciência de Dados e Estatística": 30,
    "Engenharia de Dados": 25,
    "Inteligência Artificial": 25,
    "TI Geral": 20,
}

# Intervalos base de revisão geral (D1, D7, D15, D30, D60)
INTERVALOS_REVISAO_BASE: list[tuple[str, int]] = [
    ("D1", 1),
    ("D7", 7),
    ("D15", 15),
    ("D30", 30),
    ("D60", 60),
]
