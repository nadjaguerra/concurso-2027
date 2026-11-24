"""Modelos SQLAlchemy 2.0 completos da Plataforma Concurso 2027."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    """Mixin padrão de auditoria temporal."""

    criado_em: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )


class FonteReferencia(Base, TimestampMixin):
    """Fonte oficial ou documental rastreável."""

    __tablename__ = "fonte_referencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_fonte: Mapped[str] = mapped_column(String(50), nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    orgao_emissor: Mapped[Optional[str]] = mapped_column(String(150))
    url: Mapped[Optional[str]] = mapped_column(String(800))
    caminho_arquivo_local: Mapped[Optional[str]] = mapped_column(String(500))
    data_publicacao: Mapped[Optional[date]] = mapped_column(Date)
    data_ultima_consulta: Mapped[Optional[date]] = mapped_column(Date)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)


class Banca(Base, TimestampMixin):
    """Banca organizadora de concursos."""

    __tablename__ = "banca"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sigla: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    nome_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    estilo_predominante: Mapped[str] = mapped_column(
        String(50), default="MULTIPLA_ESCOLHA"
    )
    padroes_cobranca: Mapped[Optional[str]] = mapped_column(Text)
    observacoes_perfil: Mapped[Optional[str]] = mapped_column(Text)


class Concurso(Base, TimestampMixin):
    """Concurso prioritário ou oportunidade monitorada no Radar."""

    __tablename__ = "concurso"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    orgao: Mapped[str] = mapped_column(String(250), nullable=False)
    sigla_orgao: Mapped[str] = mapped_column(String(60), nullable=False)
    esfera: Mapped[str] = mapped_column(String(40), default="FEDERAL")
    eixo_estrategico: Mapped[str] = mapped_column(
        String(50), default="EIXO_1_SEFAZ_PE"
    )  # EIXO_1_SEFAZ_PE (60%) ou EIXO_2_ANPD_TI (40%)
    peso_estrategico_percentual: Mapped[float] = mapped_column(Float, default=0.0)
    area_foco: Mapped[str] = mapped_column(String(120), default="Administrativa/Fiscal")
    banca_id: Mapped[Optional[int]] = mapped_column(ForeignKey("banca.id"))
    status_concurso: Mapped[str] = mapped_column(
        String(60), nullable=False
    )  # OFICIAL_PUBLICADO, AUTORIZADO_ANUNCIADO, HISTORICO, PROJECAO_EXPECTATIVA
    prioridade_usuario: Mapped[str] = mapped_column(
        String(50), default="NUCLEO_PRIORITARIO"
    )  # NUCLEO_PRIORITARIO, REFERENCIA_TECNICA, RADAR_OPORTUNIDADE
    requisitos_cargo: Mapped[Optional[str]] = mapped_column(Text)
    formacao_exigida: Mapped[Optional[str]] = mapped_column(String(250))
    remuneracao_informada: Mapped[Optional[str]] = mapped_column(String(200))
    fonte_remuneracao: Mapped[Optional[str]] = mapped_column(String(250))
    compatibilidade_formacao: Mapped[float] = mapped_column(Float, default=100.0)
    compatibilidade_assuntos: Mapped[float] = mapped_column(Float, default=0.0)
    ativo_no_planejamento: Mapped[bool] = mapped_column(Boolean, default=False)
    data_prevista_edital: Mapped[Optional[date]] = mapped_column(Date)
    data_prevista_prova: Mapped[Optional[date]] = mapped_column(Date)
    link_oficial: Mapped[Optional[str]] = mapped_column(String(600))
    fonte_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fonte_referencia.id"))
    data_ultima_consulta: Mapped[Optional[date]] = mapped_column(Date)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)

    banca: Mapped[Optional[Banca]] = relationship("Banca")
    cargos: Mapped[list[Cargo]] = relationship(
        "Cargo", back_populates="concurso", cascade="all, delete-orphan"
    )
    editais: Mapped[list[Edital]] = relationship(
        "Edital", back_populates="concurso", cascade="all, delete-orphan"
    )


class Cargo(Base, TimestampMixin):
    """Cargo específico dentro de um concurso."""

    __tablename__ = "cargo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concurso_id: Mapped[int] = mapped_column(
        ForeignKey("concurso.id", ondelete="CASCADE"), nullable=False
    )
    nome_cargo: Mapped[str] = mapped_column(String(250), nullable=False)
    area_especialidade: Mapped[Optional[str]] = mapped_column(String(200))
    escolaridade: Mapped[str] = mapped_column(String(120), default="Nível Superior")
    vagas_imediatas: Mapped[Optional[int]] = mapped_column(Integer)
    cadastro_reserva: Mapped[Optional[int]] = mapped_column(Integer)
    remuneracao_descricao: Mapped[Optional[str]] = mapped_column(String(300))
    jornada_semanal: Mapped[Optional[str]] = mapped_column(String(80))
    cargo_alvo_principal: Mapped[bool] = mapped_column(Boolean, default=True)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)

    concurso: Mapped[Concurso] = relationship("Concurso", back_populates="cargos")


class Edital(Base, TimestampMixin):
    """Edital, Termo de Referência ou ato oficial de concurso."""

    __tablename__ = "edital"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concurso_id: Mapped[int] = mapped_column(
        ForeignKey("concurso.id", ondelete="CASCADE"), nullable=False
    )
    cargo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cargo.id"))
    numero_ano: Mapped[str] = mapped_column(String(120), nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo_documento: Mapped[str] = mapped_column(
        String(60), default="EDITAL_ABERTURA"
    )  # EDITAL_ABERTURA, TERMO_REFERENCIA, AUTORIZACAO_BANCA, COMUNICADO
    natureza_referencia: Mapped[str] = mapped_column(
        String(60), default="HISTORICO_REFERENCIA"
    )  # OFICIAL_PUBLICADO, HISTORICO_REFERENCIA, PRELIMINAR_TR
    data_publicacao: Mapped[Optional[date]] = mapped_column(Date)
    material_id: Mapped[Optional[int]] = mapped_column(ForeignKey("material.id"))
    fonte_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fonte_referencia.id"))
    resumo_estrutura_prova: Mapped[Optional[str]] = mapped_column(Text)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)

    concurso: Mapped[Concurso] = relationship("Concurso", back_populates="editais")


class Disciplina(Base, TimestampMixin):
    """Catálogo único de disciplinas (sem duplicação entre concursos)."""

    __tablename__ = "disciplina"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    area_tematica: Mapped[str] = mapped_column(String(120), nullable=False)
    eixo_associado: Mapped[str] = mapped_column(
        String(60), default="AMBOS_COMUM"
    )  # EIXO_1_SEFAZ_PE, EIXO_2_ANPD_TI, AMBOS_COMUM
    eh_frente_tecnologica: Mapped[bool] = mapped_column(Boolean, default=False)
    categoria_tecnologica: Mapped[Optional[str]] = mapped_column(
        String(80)
    )  # CIENCIA_DADOS_ESTATISTICA (30%), ENGENHARIA_DADOS (25%), INTELIGENCIA_ARTIFICIAL (25%), TI_GERAL (20%)
    percentual_interno_tecnologia: Mapped[Optional[float]] = mapped_column(Float)
    eh_densa_legislacao: Mapped[bool] = mapped_column(Boolean, default=False)
    ordem_exibicao: Mapped[int] = mapped_column(Integer, default=10)
    descricao: Mapped[Optional[str]] = mapped_column(Text)

    topicos: Mapped[list[Topico]] = relationship(
        "Topico", back_populates="disciplina", cascade="all, delete-orphan"
    )


class Topico(Base, TimestampMixin):
    """Tópico/Assunto/Subassunto único na Matriz Integrada de Conteúdos."""

    __tablename__ = "topico"
    __table_args__ = (
        UniqueConstraint("disciplina_id", "titulo", name="uq_topico_disciplina_titulo"),
        Index("idx_topico_disciplina_pai", "disciplina_id", "topico_pai_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_estavel: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    disciplina_id: Mapped[int] = mapped_column(
        ForeignKey("disciplina.id", ondelete="CASCADE"), nullable=False
    )
    topico_pai_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    nivel_granularidade: Mapped[str] = mapped_column(
        String(40), default="ASSUNTO"
    )  # ASSUNTO, SUBASSUNTO, TOPICO_ESPECIFICO
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    descricao_objetiva: Mapped[Optional[str]] = mapped_column(Text)
    eh_denso: Mapped[bool] = mapped_column(Boolean, default=False)
    estimativa_esforco_minutos: Mapped[int] = mapped_column(Integer, default=60)
    meta_questoes: Mapped[int] = mapped_column(Integer, default=20)
    prerequisitos_codigos_json: Mapped[Optional[str]] = mapped_column(Text)
    status_estudo: Mapped[str] = mapped_column(
        String(50), default="NAO_INICIADO"
    )  # NAO_INICIADO, MATERIAL_LOCALIZADO, EM_ESTUDO, ESTUDADO, EM_REVISAO, DOMINADO
    situacao_dominio: Mapped[str] = mapped_column(
        String(50), default="NAO_AVALIADO"
    )  # NAO_AVALIADO, INICIAL, EM_DESENVOLVIMENTO, BOM, CONSOLIDADO
    score_importancia: Mapped[float] = mapped_column(Float, default=5.0)
    origem_documental: Mapped[Optional[str]] = mapped_column(String(300))
    fonte_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fonte_referencia.id"))
    validado_na_matriz: Mapped[bool] = mapped_column(Boolean, default=True)

    disciplina: Mapped[Disciplina] = relationship("Disciplina", back_populates="topicos")
    associacoes_concurso: Mapped[list[AssociacaoTopicoConcurso]] = relationship(
        "AssociacaoTopicoConcurso",
        back_populates="topico",
        cascade="all, delete-orphan",
    )


class AssociacaoTopicoConcurso(Base, TimestampMixin):
    """Associação de 1 tópico da Matriz para N concursos/editais (identifica comuns vs exclusivos)."""

    __tablename__ = "associacao_topico_concurso"
    __table_args__ = (
        UniqueConstraint(
            "topico_id", "concurso_id", name="uq_assoc_topico_concurso"
        ),
        Index("idx_assoc_concurso_status", "concurso_id", "status_no_concurso"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topico_id: Mapped[int] = mapped_column(
        ForeignKey("topico.id", ondelete="CASCADE"), nullable=False
    )
    concurso_id: Mapped[int] = mapped_column(
        ForeignKey("concurso.id", ondelete="CASCADE"), nullable=False
    )
    cargo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cargo.id"))
    edital_id: Mapped[Optional[int]] = mapped_column(ForeignKey("edital.id"))
    status_no_concurso: Mapped[str] = mapped_column(
        String(60), default="HISTORICO_REFERENCIA"
    )  # CONFIRMADO_EDITAL, HISTORICO_REFERENCIA, COMPLEMENTAR, PENDENTE_CONFIRMACAO
    item_edital_referencia: Mapped[Optional[str]] = mapped_column(String(200))
    peso_prioridade: Mapped[float] = mapped_column(Float, default=1.0)
    fundamento_peso: Mapped[Optional[str]] = mapped_column(String(300))

    topico: Mapped[Topico] = relationship(
        "Topico", back_populates="associacoes_concurso"
    )
    concurso: Mapped[Concurso] = relationship("Concurso")


class Material(Base, TimestampMixin):
    """Documento indexado da Biblioteca Documental (sem mover nem alterar o original)."""

    __tablename__ = "material"
    __table_args__ = (
        Index("idx_material_pasta_utilidade", "pasta_acervo", "classificacao_utilidade"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome_arquivo: Mapped[str] = mapped_column(String(350), nullable=False)
    caminho_relativo: Mapped[str] = mapped_column(
        String(600), unique=True, nullable=False
    )
    caminho_historico_inventario: Mapped[Optional[str]] = mapped_column(String(600))
    pasta_acervo: Mapped[str] = mapped_column(String(100), nullable=False)
    extensao: Mapped[str] = mapped_column(String(30), nullable=False)
    formato_real_verificado: Mapped[str] = mapped_column(
        String(60), default="VERIFICADO"
    )  # PDF_VALIDO, HTML_VALIDO, HTML_SPA_INCOMPLETO, MD_VALIDO, CSV_VALIDO, XLSX_VALIDO, NDJSON_VALIDO, ARQUIVO_INVALIDO
    existe_em_disco: Mapped[bool] = mapped_column(Boolean, default=True)
    eh_digitalizado_sem_texto: Mapped[bool] = mapped_column(Boolean, default=False)
    falha_leitura: Mapped[bool] = mapped_column(Boolean, default=False)
    detalhe_leitura: Mapped[Optional[str]] = mapped_column(String(400))
    numero_paginas: Mapped[Optional[int]] = mapped_column(Integer)
    texto_extraido_amostra: Mapped[Optional[str]] = mapped_column(Text)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, default=0)
    hash_sha256: Mapped[Optional[str]] = mapped_column(String(80))
    data_modificacao_disco: Mapped[Optional[datetime]] = mapped_column(DateTime)
    titulo_catalogo: Mapped[str] = mapped_column(String(400), nullable=False)
    classificacao_utilidade: Mapped[str] = mapped_column(
        String(80), default="1. APROVADO PARA ESTUDO"
    )
    tipo_material: Mapped[str] = mapped_column(
        String(80), default="DOCUMENTO_OFICIAL"
    )  # EDITAL, LEGISLACAO, GUIA_MANUAL, PROVA_OBJETIVA, PROVA_DISCURSIVA, GABARITO, RELATORIO_INVENTARIO
    disciplina_id: Mapped[Optional[int]] = mapped_column(ForeignKey("disciplina.id"))
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    concurso_id: Mapped[Optional[int]] = mapped_column(ForeignKey("concurso.id"))
    banca_nome: Mapped[Optional[str]] = mapped_column(String(120))
    orgao_referencia: Mapped[Optional[str]] = mapped_column(String(150))
    ano_referencia: Mapped[Optional[str]] = mapped_column(String(40))
    situacao_leitura: Mapped[str] = mapped_column(String(40), default="NAO_LIDO")
    url_origem: Mapped[Optional[str]] = mapped_column(String(800))
    fonte_confirmada: Mapped[Optional[str]] = mapped_column(String(250))
    alerta_auditoria: Mapped[Optional[str]] = mapped_column(Text)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)


class AssociacaoMaterialTopico(Base, TimestampMixin):
    """Permite associar vários materiais a um mesmo assunto/tópico."""

    __tablename__ = "associacao_material_topico"
    __table_args__ = (
        UniqueConstraint("material_id", "topico_id", name="uq_material_topico"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("material.id", ondelete="CASCADE"), nullable=False
    )
    topico_id: Mapped[int] = mapped_column(
        ForeignKey("topico.id", ondelete="CASCADE"), nullable=False
    )
    tipo_vinculo: Mapped[str] = mapped_column(String(60), default="PRINCIPAL")


class NormaJuridica(Base, TimestampMixin):
    """Cadastro estruturado de Legislação com controle de versão e fonte oficial."""

    __tablename__ = "norma_juridica"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_norma: Mapped[str] = mapped_column(
        String(80), nullable=False
    )  # CONSTITUICAO_FEDERAL, CONSTITUICAO_ESTADUAL, LEI_COMPLEMENTAR, LEI_ORDINARIA, DECRETO_LEI, DECRETO, RESOLUCAO, ENUNCIADO, CODIGO, ATO_NORMATIVO
    jurisdicao: Mapped[str] = mapped_column(String(40), default="FEDERAL")
    numero: Mapped[str] = mapped_column(String(80), nullable=False)
    ano: Mapped[str] = mapped_column(String(20), nullable=False)
    titulo_curto: Mapped[str] = mapped_column(String(250), nullable=False)
    ementa: Mapped[str] = mapped_column(Text, nullable=False)
    artigos_chave: Mapped[Optional[str]] = mapped_column(Text)
    fonte_oficial_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    fonte_oficial_url: Mapped[Optional[str]] = mapped_column(String(800))
    data_atualizacao_verificada: Mapped[Optional[date]] = mapped_column(Date)
    versao_controle: Mapped[str] = mapped_column(
        String(100), default="Texto Compilado Oficial Local"
    )
    historico_alteracoes_legislativas: Mapped[Optional[str]] = mapped_column(Text)
    status_vigencia: Mapped[str] = mapped_column(
        String(80), default="VIGENTE_VERIFICADA_EM_FONTE"
    )
    status_leitura: Mapped[str] = mapped_column(String(50), default="NAO_LIDA")
    nivel_dominio: Mapped[str] = mapped_column(String(50), default="NAO_AVALIADO")
    disciplina_id: Mapped[Optional[int]] = mapped_column(ForeignKey("disciplina.id"))
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    concurso_id: Mapped[Optional[int]] = mapped_column(ForeignKey("concurso.id"))
    material_html_id: Mapped[Optional[int]] = mapped_column(ForeignKey("material.id"))
    material_pdf_id: Mapped[Optional[int]] = mapped_column(ForeignKey("material.id"))


class HistoricoProvaCobranca(Base, TimestampMixin):
    """Inteligência de Cobrança e Histórico de Provas Anteriores (Seção 10)."""

    __tablename__ = "historico_prova_cobranca"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    banca_id: Mapped[Optional[int]] = mapped_column(ForeignKey("banca.id"))
    banca_sigla: Mapped[str] = mapped_column(String(60), nullable=False)
    concurso_nome: Mapped[str] = mapped_column(String(250), nullable=False)
    cargo_nome: Mapped[str] = mapped_column(String(250), nullable=False)
    ano_prova: Mapped[int] = mapped_column(Integer, nullable=False)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    assunto_cobrado: Mapped[str] = mapped_column(String(300), nullable=False)
    quantidade_questoes_assunto: Mapped[int] = mapped_column(Integer, nullable=False)
    total_questoes_prova: Mapped[int] = mapped_column(Integer, nullable=False)
    frequencia_percentual: Mapped[float] = mapped_column(Float, nullable=False)
    classificacao_recorrencia: Mapped[str] = mapped_column(
        String(60), default="RECORRENTE"
    )  # MUITO_RECORRENTE, RECORRENTE, OCASIONAL, POUCO_COBRADO
    evidencias_utilizadas: Mapped[str] = mapped_column(Text, nullable=False)
    quantidade_provas_analisadas: Mapped[int] = mapped_column(Integer, default=1)
    periodo_considerado: Mapped[str] = mapped_column(String(80), default="2021-2026")
    metodo_utilizado: Mapped[str] = mapped_column(
        String(250),
        default="Contagem direta em caderno de prova e gabarito oficial do acervo local",
    )
    nivel_confianca_analise: Mapped[str] = mapped_column(
        String(60), default="ALTO_EVIDENCIA_DIRETA"
    )
    limitacoes_analise: Mapped[str] = mapped_column(
        Text,
        default="Baseado nas provas oficiais presentes no acervo; não representa previsão garantida para editais futuros.",
    )
    material_prova_id: Mapped[Optional[int]] = mapped_column(ForeignKey("material.id"))


class AvaliacaoNivelamento(Base, TimestampMixin):
    """Diagnóstico de conhecimento por disciplina e assunto (Seção 11)."""

    __tablename__ = "avaliacao_nivelamento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_avaliacao: Mapped[date] = mapped_column(Date, nullable=False)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    origem_diagnostico: Mapped[str] = mapped_column(
        String(80), default="BATERIA_DIAGNOSTICA"
    )
    questoes_avaliadas: Mapped[int] = mapped_column(Integer, default=0)
    acertos: Mapped[int] = mapped_column(Integer, default=0)
    erros: Mapped[int] = mapped_column(Integer, default=0)
    tempo_resposta_segundos: Mapped[int] = mapped_column(Integer, default=0)
    confianca: Mapped[str] = mapped_column(String(40), default="MEDIA")
    dificuldade_percebida: Mapped[int] = mapped_column(Integer, default=3)
    classificacao_dominio: Mapped[str] = mapped_column(
        String(60), nullable=False
    )  # NAO_AVALIADO, INICIAL, EM_DESENVOLVIMENTO, BOM, CONSOLIDADO
    recomendacao_gerada: Mapped[Optional[str]] = mapped_column(Text)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)


class EntendimentoJurisprudencia(Base, TimestampMixin):
    """Biblioteca de Súmulas, Jurisprudência, Informativos, Repercussão Geral e Repetitivos com SM-2 (Seção 20)."""

    __tablename__ = "entendimento_jurisprudencia"
    __table_args__ = (
        Index("idx_juris_tribunal_tipo", "tribunal", "tipo_entendimento"),
        Index("idx_juris_sm2_proxima", "sm2_proxima_revisao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tribunal: Mapped[str] = mapped_column(
        String(60), nullable=False
    )  # STF, STJ, STF_VINCULANTE, TCU, ANPD, TSE, OUTRO
    tipo_entendimento: Mapped[str] = mapped_column(
        String(80), nullable=False
    )  # SUMULA_VINCULANTE, SUMULA_STF, SUMULA_STJ, INFORMATIVO, REPERCUSSAO_GERAL, RECURSO_REPETITIVO, JURISPRUDENCIA_RELEVANTE, ENUNCIADO_ANPD
    numero_identificacao: Mapped[str] = mapped_column(String(120), nullable=False)
    disciplina_id: Mapped[Optional[int]] = mapped_column(ForeignKey("disciplina.id"))
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    assunto_titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    texto_entendimento: Mapped[str] = mapped_column(Text, nullable=False)
    resumo_didatico: Mapped[Optional[str]] = mapped_column(Text)
    data_publicacao: Mapped[Optional[date]] = mapped_column(Date)
    data_atualizacao_verificada: Mapped[Optional[date]] = mapped_column(Date)
    situacao_vigencia: Mapped[str] = mapped_column(
        String(60), default="VIGENTE_VERIFICADA"
    )
    fonte_oficial: Mapped[str] = mapped_column(String(250), nullable=False)
    link_origem: Mapped[Optional[str]] = mapped_column(String(800))
    concursos_relacionados: Mapped[str] = mapped_column(
        String(150), default="SEFAZ-PE, ANPD"
    )
    favorito: Mapped[bool] = mapped_column(Boolean, default=False)
    anotacoes_pessoais: Mapped[Optional[str]] = mapped_column(Text)
    compreensao_registrada: Mapped[Optional[str]] = mapped_column(Text)
    dificuldade_percebida: Mapped[int] = mapped_column(Integer, default=3)
    total_acertos: Mapped[int] = mapped_column(Integer, default=0)
    total_erros: Mapped[int] = mapped_column(Integer, default=0)
    estimativa_dominio: Mapped[str] = mapped_column(
        String(50), default="NAO_ESTUDADO"
    )  # NAO_ESTUDADO, INICIAL, INTERMEDIARIO, CONSOLIDADO
    # Campos do Algoritmo SM-2 (SuperMemo 2) específico de Jurisprudência/Súmulas
    sm2_repeticoes: Mapped[int] = mapped_column(Integer, default=0)
    sm2_easiness_factor: Mapped[float] = mapped_column(Float, default=2.5)
    sm2_intervalo_dias: Mapped[int] = mapped_column(Integer, default=0)
    sm2_ultima_revisao: Mapped[Optional[date]] = mapped_column(Date)
    sm2_proxima_revisao: Mapped[Optional[date]] = mapped_column(Date)
    historico_estudo_json: Mapped[Optional[str]] = mapped_column(Text)


class Revisao(Base, TimestampMixin):
    """Revisão Geral Espaçada D1/D7/D15/D30/D60 (Etapa 1 do Meu Dia)."""

    __tablename__ = "revisao"
    __table_args__ = (Index("idx_revisao_status_data", "status_revisao", "data_prevista"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topico_id: Mapped[int] = mapped_column(ForeignKey("topico.id"), nullable=False)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    sessao_origem_id: Mapped[Optional[int]] = mapped_column(Integer)
    ciclo_revisao: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # D1, D7, D15, D30, D60, REFORCO_ERRO
    modalidade_revisao: Mapped[str] = mapped_column(
        String(80), default="Recuperação Ativa + Legislação + Questões"
    )
    intervalo_dias_aplicado: Mapped[int] = mapped_column(Integer, nullable=False)
    data_prevista: Mapped[date] = mapped_column(Date, nullable=False)
    data_realizada: Mapped[Optional[date]] = mapped_column(Date)
    status_revisao: Mapped[str] = mapped_column(
        String(40), default="PENDENTE"
    )  # PENDENTE, ATRASADA, CONCLUIDA, ADIADA
    dificuldade_na_revisao: Mapped[Optional[int]] = mapped_column(Integer)
    confianca_na_revisao: Mapped[Optional[str]] = mapped_column(String(30))
    percentual_acerto_revisao: Mapped[Optional[float]] = mapped_column(Float)
    autoavaliacao: Mapped[Optional[str]] = mapped_column(Text)
    justificativa_adiamento: Mapped[Optional[str]] = mapped_column(Text)


class TarefaCronograma(Base, TimestampMixin):
    """Tarefa diária estruturada nas 4 Etapas Obrigatórias do Meu Dia."""

    __tablename__ = "tarefa_cronograma"
    __table_args__ = (
        Index("idx_tarefa_data_etapa", "data_programada", "etapa_meu_dia", "ordem_no_dia"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_programada: Mapped[date] = mapped_column(Date, nullable=False)
    etapa_meu_dia: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 1=REVISOES, 2=CONTEUDO_NOVO, 3=JURISPRUDENCIA_SUMULA, 4=REGISTRO_APRENDIZADO
    nome_etapa: Mapped[str] = mapped_column(String(80), nullable=False)
    ordem_no_dia: Mapped[int] = mapped_column(Integer, default=1)
    eixo_estrategico: Mapped[str] = mapped_column(
        String(60), default="EIXO_1_SEFAZ_PE"
    )
    disciplina_id: Mapped[Optional[int]] = mapped_column(ForeignKey("disciplina.id"))
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    revisao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("revisao.id"))
    jurisprudencia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("entendimento_jurisprudencia.id")
    )
    titulo_tarefa: Mapped[str] = mapped_column(String(350), nullable=False)
    duracao_planejada_minutos: Mapped[int] = mapped_column(Integer, default=60)
    duracao_realizada_minutos: Mapped[int] = mapped_column(Integer, default=0)
    questoes_planejadas: Mapped[int] = mapped_column(Integer, default=10)
    status_tarefa: Mapped[str] = mapped_column(
        String(40), default="PENDENTE"
    )  # PENDENTE, EM_ANDAMENTO, CONCLUIDA, TRANSFERIDA
    motivo_recomendacao: Mapped[str] = mapped_column(Text, nullable=False)
    justificativa_transferencia: Mapped[Optional[str]] = mapped_column(Text)


class SessaoEstudo(Base, TimestampMixin):
    """Registro de Aprendizado (Etapa 4 do Meu Dia)."""

    __tablename__ = "sessao_estudo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_sessao: Mapped[date] = mapped_column(Date, nullable=False)
    inicio_em: Mapped[Optional[datetime]] = mapped_column(DateTime)
    fim_em: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duracao_minutos: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo_sessao: Mapped[str] = mapped_column(
        String(50), default="CONTEUDO_NOVO"
    )  # REVISAO, CONTEUDO_NOVO, JURISPRUDENCIA_SUMULA, QUESTOES, SIMULADO
    status_execucao: Mapped[str] = mapped_column(String(40), default="CONCLUIDA")
    eixo_estrategico: Mapped[str] = mapped_column(
        String(60), default="EIXO_1_SEFAZ_PE"
    )
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    material_id: Mapped[Optional[int]] = mapped_column(ForeignKey("material.id"))
    tarefa_cronograma_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tarefa_cronograma.id")
    )
    revisao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("revisao.id"))
    jurisprudencia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("entendimento_jurisprudencia.id")
    )
    questoes_realizadas: Mapped[int] = mapped_column(Integer, default=0)
    acertos: Mapped[int] = mapped_column(Integer, default=0)
    erros: Mapped[int] = mapped_column(Integer, default=0)
    dificuldade_percebida: Mapped[int] = mapped_column(Integer, default=3)
    grau_compreensao: Mapped[str] = mapped_column(
        String(40), default="BOM"
    )  # BAIXO, REGULAR, BOM, EXCELENTE
    nivel_confianca: Mapped[str] = mapped_column(
        String(40), default="MEDIA"
    )  # BAIXA, MEDIA, ALTA
    observacoes: Mapped[Optional[str]] = mapped_column(Text)


class Questao(Base, TimestampMixin):
    """Questão registrada manualmente ou extraída de prova oficial do acervo."""

    __tablename__ = "questao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_externo_qconcursos: Mapped[Optional[str]] = mapped_column(String(100))
    link_externo_qconcursos: Mapped[Optional[str]] = mapped_column(String(800))
    natureza_questao: Mapped[str] = mapped_column(
        String(60), default="OFICIAL_ACERVO"
    )  # OFICIAL_ACERVO, REGISTRO_MANUAL_QCONCURSOS, QUESTAO_TREINO_PLATAFORMA
    concurso_referencia: Mapped[Optional[str]] = mapped_column(String(200))
    banca_id: Mapped[Optional[int]] = mapped_column(ForeignKey("banca.id"))
    banca_nome: Mapped[str] = mapped_column(String(80), default="Cebraspe")
    ano: Mapped[Optional[int]] = mapped_column(Integer)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    subassunto: Mapped[Optional[str]] = mapped_column(String(250))
    modalidade: Mapped[str] = mapped_column(
        String(40), default="CERTO_ERRADO"
    )  # CERTO_ERRADO, MULTIPLA_ESCOLHA
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    alternativas_json: Mapped[Optional[str]] = mapped_column(Text)
    gabarito: Mapped[str] = mapped_column(String(30), nullable=False)
    comentario_explicacao: Mapped[Optional[str]] = mapped_column(Text)
    dificuldade: Mapped[str] = mapped_column(String(40), default="MEDIA")
    fonte_origem: Mapped[str] = mapped_column(
        String(300), nullable=False
    )
    material_prova_id: Mapped[Optional[int]] = mapped_column(ForeignKey("material.id"))
    jurisprudencia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("entendimento_jurisprudencia.id")
    )
    norma_id: Mapped[Optional[int]] = mapped_column(ForeignKey("norma_juridica.id"))


class SessaoQuestoes(Base, TimestampMixin):
    """Bateria de resolução de questões (local ou Qconcursos)."""

    __tablename__ = "sessao_questoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_resolucao: Mapped[date] = mapped_column(Date, nullable=False)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    banca_nome: Mapped[Optional[str]] = mapped_column(String(80))
    concurso_referencia: Mapped[Optional[str]] = mapped_column(String(200))
    plataforma_origem: Mapped[str] = mapped_column(
        String(60), default="QCONCURSOS"
    )  # QCONCURSOS, ACERVO_LOCAL, PLATAFORMA_2027
    link_caderno_qconcursos: Mapped[Optional[str]] = mapped_column(String(800))
    total_questoes: Mapped[int] = mapped_column(Integer, nullable=False)
    acertos: Mapped[int] = mapped_column(Integer, nullable=False)
    erros: Mapped[int] = mapped_column(Integer, nullable=False)
    tempo_minutos: Mapped[int] = mapped_column(Integer, default=0)
    confianca_media: Mapped[str] = mapped_column(String(40), default="MEDIA")
    dificuldade_media: Mapped[str] = mapped_column(String(40), default="MEDIA")
    comentarios: Mapped[Optional[str]] = mapped_column(Text)


class RespostaQuestao(Base, TimestampMixin):
    """Registro individual de resolução de questão."""

    __tablename__ = "resposta_questao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    questao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("questao.id"))
    sessao_questoes_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sessao_questoes.id")
    )
    simulado_id: Mapped[Optional[int]] = mapped_column(ForeignKey("simulado.id"))
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    banca_nome: Mapped[Optional[str]] = mapped_column(String(80))
    concurso_nome: Mapped[Optional[str]] = mapped_column(String(200))
    fonte_link_externo: Mapped[Optional[str]] = mapped_column(String(800))
    data_resolucao: Mapped[date] = mapped_column(Date, nullable=False)
    resposta_escolhida: Mapped[str] = mapped_column(String(40), nullable=False)
    gabarito_correto: Mapped[str] = mapped_column(String(40), nullable=False)
    resultado: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # CORRETA, INCORRETA, EM_BRANCO, ANULADA
    tempo_segundos: Mapped[int] = mapped_column(Integer, default=60)
    confianca: Mapped[str] = mapped_column(
        String(30), default="SABIA"
    )  # SABIA, DUVIDA, CHUTE
    dificuldade: Mapped[str] = mapped_column(String(30), default="MEDIA")
    pendente_revisao: Mapped[bool] = mapped_column(Boolean, default=False)
    comentarios: Mapped[Optional[str]] = mapped_column(Text)


class ErroCaderno(Base, TimestampMixin):
    """Caderno de Erros com as 8 categorias exigidas na Seção 16."""

    __tablename__ = "erro_caderno"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resposta_questao_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("resposta_questao.id")
    )
    questao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("questao.id"))
    referencia_questao_externa: Mapped[str] = mapped_column(String(350), nullable=False)
    link_qconcursos: Mapped[Optional[str]] = mapped_column(String(800))
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    categoria_erro: Mapped[str] = mapped_column(
        String(80), nullable=False
    )  # FALTA_CONHECIMENTO, ESQUECIMENTO, INTERPRETACAO, DESATENCAO, CONFUSAO_CONCEITOS, DESCONHECIMENTO_LEGISLACAO, ERRO_CALCULO, ERRO_ESTRATEGIA
    alternativa_escolhida: Mapped[str] = mapped_column(String(100), nullable=False)
    resposta_correta: Mapped[str] = mapped_column(String(100), nullable=False)
    explicacao_correcao: Mapped[str] = mapped_column(Text, nullable=False)
    plano_acao: Mapped[Optional[str]] = mapped_column(Text)
    dificuldade: Mapped[str] = mapped_column(String(40), default="ALTA")
    confianca: Mapped[str] = mapped_column(String(40), default="DUVIDA")
    data_erro: Mapped[date] = mapped_column(Date, nullable=False)
    revisoes_realizadas: Mapped[int] = mapped_column(Integer, default=0)
    reincidencias: Mapped[int] = mapped_column(Integer, default=1)
    status_superacao: Mapped[str] = mapped_column(
        String(40), default="PENDENTE_REFORCO"
    )  # PENDENTE_REFORCO, EM_REVISAO, SUPERADO
    proxima_revisao_em: Mapped[Optional[date]] = mapped_column(Date)


class Flashcard(Base, TimestampMixin):
    """Sistema de Flashcards com repetição espaçada SM-2 (Seção 17)."""

    __tablename__ = "flashcard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    frente_pergunta: Mapped[str] = mapped_column(Text, nullable=False)
    verso_resposta: Mapped[str] = mapped_column(Text, nullable=False)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplina.id"), nullable=False)
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))
    norma_id: Mapped[Optional[int]] = mapped_column(ForeignKey("norma_juridica.id"))
    jurisprudencia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("entendimento_jurisprudencia.id")
    )
    dificuldade: Mapped[str] = mapped_column(String(40), default="MEDIA")
    dominio_avaliado: Mapped[str] = mapped_column(String(40), default="EM_APRENDIZADO")
    algoritmo_utilizado: Mapped[str] = mapped_column(String(30), default="SM-2")
    sm2_repeticoes: Mapped[int] = mapped_column(Integer, default=0)
    sm2_easiness_factor: Mapped[float] = mapped_column(Float, default=2.5)
    sm2_intervalo_dias: Mapped[int] = mapped_column(Integer, default=0)
    ultima_revisao_em: Mapped[Optional[date]] = mapped_column(Date)
    proxima_revisao_em: Mapped[Optional[date]] = mapped_column(Date)
    total_revisoes: Mapped[int] = mapped_column(Integer, default=0)
    historico_json: Mapped[Optional[str]] = mapped_column(Text)


class Simulado(Base, TimestampMixin):
    """Simulado configurável e adaptativo (Seção 18)."""

    __tablename__ = "simulado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    concurso_id: Mapped[Optional[int]] = mapped_column(ForeignKey("concurso.id"))
    banca_estilo: Mapped[str] = mapped_column(
        String(80), default="Cebraspe (Certo/Errado)"
    )
    modo_selecao: Mapped[str] = mapped_column(
        String(60), default="ADAPTATIVO_PONTOS_FRACOS"
    )  # PADRAO_EQUILIBRADO, ADAPTATIVO_PONTOS_FRACOS
    quantidade_questoes: Mapped[int] = mapped_column(Integer, nullable=False)
    tempo_previsto_minutos: Mapped[int] = mapped_column(Integer, default=120)
    disciplinas_selecionadas_json: Mapped[Optional[str]] = mapped_column(Text)
    questoes_ids_json: Mapped[Optional[str]] = mapped_column(Text)
    origem_questoes_aviso: Mapped[str] = mapped_column(
        String(300),
        default="Questões cadastradas no banco local com origem identificada (Oficial do Acervo ou Treino identificado).",
    )
    status_simulado: Mapped[str] = mapped_column(
        String(40), default="CRIADO"
    )  # CRIADO, EM_ANDAMENTO, CONCLUIDO
    data_realizacao: Mapped[Optional[date]] = mapped_column(Date)


class ResultadoSimulado(Base, TimestampMixin):
    """Resultado consolidado de um simulado e diagnóstico de pontos fracos."""

    __tablename__ = "resultado_simulado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulado_id: Mapped[int] = mapped_column(
        ForeignKey("simulado.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    tempo_gasto_minutos: Mapped[int] = mapped_column(Integer, default=0)
    total_questoes: Mapped[int] = mapped_column(Integer, nullable=False)
    acertos: Mapped[int] = mapped_column(Integer, nullable=False)
    erros: Mapped[int] = mapped_column(Integer, nullable=False)
    em_branco: Mapped[int] = mapped_column(Integer, default=0)
    pontuacao_liquida_cebraspe: Mapped[float] = mapped_column(Float, default=0.0)
    percentual_acerto: Mapped[float] = mapped_column(Float, default=0.0)
    pontos_fracos_identificados_json: Mapped[Optional[str]] = mapped_column(Text)
    desempenho_por_disciplina_json: Mapped[Optional[str]] = mapped_column(Text)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)


class MetaAlerta(Base, TimestampMixin):
    """Sistema de Metas e Alertas configuráveis (Seção 22)."""

    __tablename__ = "meta_alerta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_registro: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # META, ALERTA
    categoria: Mapped[str] = mapped_column(
        String(80), nullable=False
    )  # META_QUESTOES_ASSUNTO, META_HORAS_SEMANAL, REVISAO_ATRASADA, BAIXO_DESEMPENHO, DOCUMENTO_SEM_CLASSIFICACAO, ATUALIZACAO_LEGISLATIVA, OPORTUNIDADE_RADAR, SIMULADO_PENDENTE
    titulo: Mapped[str] = mapped_column(String(250), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    valor_alvo: Mapped[Optional[float]] = mapped_column(Float)
    valor_atual: Mapped[Optional[float]] = mapped_column(Float)
    prioridade: Mapped[str] = mapped_column(String(40), default="MEDIA")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    resolvido: Mapped[bool] = mapped_column(Boolean, default=False)
    disciplina_id: Mapped[Optional[int]] = mapped_column(ForeignKey("disciplina.id"))
    topico_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topico.id"))


class Configuracao(Base, TimestampMixin):
    """Parâmetros globais e estratégicos persistidos no SQLite."""

    __tablename__ = "configuracao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chave: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    valor_json: Mapped[str] = mapped_column(Text, nullable=False)
    categoria: Mapped[str] = mapped_column(String(60), default="GERAL")
    descricao: Mapped[Optional[str]] = mapped_column(String(300))


class AuditoriaAlteracao(Base):
    """Trilha de auditoria das alterações na matriz, legislação e importações."""

    __tablename__ = "auditoria_alteracao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entidade_nome: Mapped[str] = mapped_column(String(100), nullable=False)
    entidade_id: Mapped[Optional[int]] = mapped_column(Integer)
    acao: Mapped[str] = mapped_column(String(50), nullable=False)
    resumo_alteracao: Mapped[str] = mapped_column(Text, nullable=False)
    data_hora: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
