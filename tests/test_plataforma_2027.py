"""Suíte de Testes Automatizados de Ponta a Ponta — Plataforma Concurso 2027 (Etapa 12).

Valida:
1. Inicialização da aplicação FastAPI e persistência real no SQLite.
2. Renderização e resposta de todos os 15 módulos do menu principal.
3. Indexação real dos 219 arquivos nas 6 pastas oficiais do acervo e proteção anti-Path Traversal.
4. Distribuição estratégica 60% SEFAZ-PE / 40% ANPD + Dados e TI e distribuição tecnológica interna 30/25/25/20.
5. Matriz Integrada sem duplicação de conteúdos comuns.
6. Sequência obrigatória das 4 Etapas do Meu Dia e geração automática de revisão D1 -> D7.
7. Algoritmo SM-2 em Jurisprudência/Súmulas e Flashcards + Exportação e Importação JSON com prevenção de duplicidade.
8. Questões (Qconcursos), Caderno de Erros (8 categorias), Simulados Adaptativos, Nivelamento (regra anti-1-questão), Radar e Backup SQLite com integridade e hash SHA-256.
"""
from __future__ import annotations

import json
from starlette.requests import Request
from sqlalchemy import func, select

from app.database import Base, SessionLocal, engine
from app.models.entities import (
    AssociacaoTopicoConcurso,
    Concurso,
    Disciplina,
    EntendimentoJurisprudencia,
    ErroCaderno,
    Flashcard,
    Material,
    Revisao,
    Topico,
)
from app.routers import web_router
from app.services.acervo_service import resolve_safe_file_path
from app.services.analitica_backup_service import (
    corrigir_simulado,
    criar_backup_sqlite,
    criar_simulado_adaptativo,
    exportar_jurisprudencia_json,
    importar_jurisprudencia_json,
)
from app.services.planejamento_service import calcular_sm2
from app.services.seed_service import inicializar_dados_plataforma


def _make_request(path: str = "/") -> Request:
    """Cria objeto Request Starlette/FastAPI para teste em processo sem socketpair."""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 8000),
        "server": ("127.0.0.1", 8000),
    }
    return Request(scope)


def test_1_health_e_distribuicao_estrategica_60_40():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        inicializar_dados_plataforma(db)
        data = web_router.api_health(db=db)
        assert data["status"] == "ok"
        assert data["eixos_estrategicos"]["EIXO_1_SEFAZ_PE"] == 60
        assert data["eixos_estrategicos"]["EIXO_2_ANPD_DADOS_TI"] == 40
        frente = data["eixos_estrategicos"]["frente_tecnologica_interna"]
        assert frente["Ciência de Dados e Estatística"] == 30
        assert frente["Engenharia de Dados"] == 25
        assert frente["Inteligência Artificial"] == 25
        assert frente["TI Geral"] == 20
        assert data["arquivos_acervo_indexados"] >= 215
        assert data["topicos_matriz_integrada"] >= 20
        assert data["normas_cadastradas"] >= 15
        assert data["entendimentos_jurisprudencia_sm2"] >= 8


def test_2_navegacao_15_modulos_principais():
    with SessionLocal() as db:
        paginas = [
            ("/dashboard", lambda r: web_router.pagina_dashboard(r, db=db)),
            ("/meu-dia", lambda r: web_router.pagina_meu_dia(r, db=db)),
            ("/planejamento", lambda r: web_router.pagina_planejamento(r, db=db)),
            ("/editais", lambda r: web_router.pagina_editais(r, db=db)),
            (
                "/disciplinas",
                lambda r: web_router.pagina_disciplinas(
                    r, disciplina_id=None, tipo_escopo=None, db=db
                ),
            ),
            (
                "/biblioteca",
                lambda r: web_router.pagina_biblioteca(
                    r, q=None, pasta=None, tipo=None, db=db
                ),
            ),
            (
                "/legislacao",
                lambda r: web_router.pagina_legislacao(
                    r, q=None, jurisdicao=None, db=db
                ),
            ),
            ("/questoes", lambda r: web_router.pagina_questoes_e_erros(r, db=db)),
            ("/caderno-erros", lambda r: web_router.pagina_questoes_e_erros(r, db=db)),
            ("/revisoes", lambda r: web_router.pagina_revisoes_e_simulados(r, db=db)),
            ("/simulados", lambda r: web_router.pagina_revisoes_e_simulados(r, db=db)),
            (
                "/jurisprudencia",
                lambda r: web_router.pagina_jurisprudencia(
                    r, q=None, tribunal=None, apenas_favoritos=None, db=db
                ),
            ),
            (
                "/desempenho",
                lambda r: web_router.pagina_desempenho_radar_config(r, db=db),
            ),
            ("/radar", lambda r: web_router.pagina_desempenho_radar_config(r, db=db)),
            (
                "/configuracoes",
                lambda r: web_router.pagina_desempenho_radar_config(r, db=db),
            ),
        ]
        for path, handler in paginas:
            req = _make_request(path)
            resp = handler(req)
            assert resp.status_code == 200, f"Falha na página {path}"
            body = bytes(resp.body).decode("utf-8")
            assert "PLATAFORMA 2027" in body


def test_3_acervo_indexado_e_seguranca_caminhos():
    with SessionLocal() as db:
        total_mat = db.scalar(select(func.count(Material.id))) or 0
        assert total_mat >= 215
        falhas = (
            db.scalar(
                select(func.count(Material.id)).where(Material.falha_leitura == True)  # noqa: E712
            )
            or 0
        )
        assert falhas >= 2
        primeiro = db.scalar(
            select(Material).where(Material.formato_real_verificado == "PDF_VALIDO")
        )
        assert primeiro is not None

        # Bloqueio de Path Traversal fora da raiz
        assert resolve_safe_file_path("../../Windows/System32/cmd.exe") is None

        file_resp = web_router.abrir_arquivo_acervo(primeiro.id, db=db)
        assert file_resp.media_type == "application/pdf"


def test_4_matriz_integrada_sem_duplicacao_conteudos_comuns():
    with SessionLocal() as db:
        top_licit = db.scalar(
            select(Topico).where(Topico.codigo_estavel == "DIR_ADM_01")
        )
        assert top_licit is not None
        assocs = db.scalars(
            select(AssociacaoTopicoConcurso).where(
                AssociacaoTopicoConcurso.topico_id == top_licit.id
            )
        ).all()
        assert len(assocs) >= 2

        # Tentar duplicar o mesmo código é bloqueado sem criar novo registro
        count_before = db.scalar(select(func.count(Topico.id)))
        resp = web_router.acao_novo_topico(
            codigo_estavel="DIR_ADM_01",
            disciplina_id=top_licit.disciplina_id,
            titulo=top_licit.titulo,
            escopo_concursos="AMBOS",
            db=db,
        )
        assert resp.status_code == 303
        count_after = db.scalar(select(func.count(Topico.id)))
        assert count_after == count_before


def test_5_meu_dia_4_etapas_e_ciclo_revisao_d1_d7():
    with SessionLocal() as db:
        req = _make_request("/meu-dia")
        resp = web_router.pagina_meu_dia(req, db=db)
        html = bytes(resp.body).decode("utf-8")
        assert "ETAPA 1" in html
        assert "ETAPA 2" in html
        assert "ETAPA 3" in html
        assert "ETAPA 4" in html

        top = db.scalar(select(Topico).where(Topico.codigo_estavel == "LGPD_01"))
        assert top is not None

        # Registra aprendizado na Etapa 4 -> deve agendar revisão D1
        web_router.acao_registrar_aprendizado(
            disciplina_id=top.disciplina_id,
            topico_id=str(top.id),
            tipo_sessao="CONTEUDO_NOVO",
            duracao_minutos=75,
            questoes_realizadas=12,
            acertos=10,
            dificuldade_percebida=2,
            grau_compreensao="EXCELENTE",
            nivel_confianca="ALTA",
            observacoes="Estudo completo da LGPD arts. 1 a 16",
            tarefa_id=None,
            db=db,
        )

        rev_d1 = db.scalar(
            select(Revisao)
            .where(Revisao.topico_id == top.id, Revisao.ciclo_revisao == "D1")
            .order_by(Revisao.id.desc())
        )
        assert rev_d1 is not None

        # Conclui revisão D1 -> deve agendar revisão D7
        web_router.acao_concluir_revisao(
            revisao_id=rev_d1.id,
            duracao_minutos=25,
            dificuldade=2,
            confianca="ALTA",
            db=db,
        )

        rev_d7 = db.scalar(
            select(Revisao).where(
                Revisao.topico_id == top.id,
                Revisao.ciclo_revisao == "D7",
                Revisao.status_revisao == "PENDENTE",
            )
        )
        assert rev_d7 is not None


def test_6_algoritmo_sm2_jurisprudencia_flashcards_e_json():
    rep1, ef1, int1 = calcular_sm2(5, 0, 2.5, 0)
    assert rep1 == 1 and int1 == 1 and ef1 >= 2.5
    rep2, ef2, int2 = calcular_sm2(5, rep1, ef1, int1)
    assert rep2 == 2 and int2 == 6
    rep_fail, ef_fail, int_fail = calcular_sm2(2, rep2, ef2, int2)
    assert rep_fail == 0 and int_fail == 1

    with SessionLocal() as db:
        j = db.scalar(select(EntendimentoJurisprudencia))
        fc = db.scalar(select(Flashcard))
        assert j is not None and fc is not None

        web_router.acao_revisar_jurisprudencia_sm2(
            juris_id=j.id,
            qualidade_sm2=5,
            compreensao="Domínio completo da súmula.",
            dificuldade=2,
            db=db,
        )
        db.refresh(j)
        assert j.sm2_repeticoes >= 1
        assert j.sm2_intervalo_dias >= 1

        web_router.acao_avaliar_flashcard_sm2(
            card_id=fc.id, qualidade_sm2=4, db=db
        )
        db.refresh(fc)
        assert fc.total_revisoes >= 1

        exported = exportar_jurisprudencia_json(db)
        assert exported["total_registros"] >= 8

        novo_payload = {
            "entendimentos": [
                {
                    "tribunal": "STF_VINCULANTE",
                    "tipo_entendimento": "SUMULA_VINCULANTE",
                    "numero_identificacao": "Súmula Vinculante 13",
                    "assunto_titulo": "Duplicado para teste",
                    "texto_entendimento": "Texto duplicado que deve ser ignorado.",
                    "fonte_oficial": "STF",
                },
                {
                    "tribunal": "STF_VINCULANTE",
                    "tipo_entendimento": "SUMULA_VINCULANTE",
                    "numero_identificacao": "Súmula Vinculante 21",
                    "assunto_titulo": "Inconstitucionalidade de depósito prévio em recurso administrativo",
                    "texto_entendimento": "É inconstitucional a exigência de depósito ou arrolamento prévios de dinheiro ou bens para admissibilidade de recurso administrativo.",
                    "fonte_oficial": "Portal Oficial do STF",
                },
            ]
        }
        res_imp = importar_jurisprudencia_json(
            db, novo_payload, sobrescrever_duplicados=False
        )
        assert res_imp["ignorados_duplicados"] >= 1


def test_7_questoes_caderno_erros_simulados_nivelamento_radar_e_backup():
    with SessionLocal() as db:
        disc = db.scalar(select(Disciplina).where(Disciplina.codigo == "AFO"))
        assert disc is not None

        erros_antes = db.scalar(select(func.count(ErroCaderno.id))) or 0
        web_router.acao_registrar_resposta_questao(
            disciplina_id=disc.id,
            topico_id=None,
            banca_nome="IAUPE/UPENET",
            concurso_nome="SEFAZ-PE 2022",
            resposta_escolhida="A",
            gabarito_correto="B",
            confianca="DUVIDA",
            tempo_segundos=85,
            fonte_link_externo="https://www.qconcursos.com/questoes-de-concursos/questoes/exemplo-afo",
            categoria_erro="CONFUSAO_CONCEITOS",
            comentarios="Confundi empenho com liquidação na Lei 4.320/64.",
            db=db,
        )
        erros_depois = db.scalar(select(func.count(ErroCaderno.id))) or 0
        assert erros_depois == erros_antes + 1

        # Nivelamento com 1 única questão não pode classificar como CONSOLIDADO (Regra 11)
        web_router.acao_registrar_nivelamento(
            disciplina_id=disc.id,
            topico_id=None,
            questoes_avaliadas=1,
            acertos=1,
            tempo_resposta_segundos=60,
            confianca="ALTA",
            dificuldade_percebida=2,
            db=db,
        )
        from app.models.entities import AvaliacaoNivelamento
        ult_av = db.scalar(
            select(AvaliacaoNivelamento).order_by(AvaliacaoNivelamento.id.desc())
        )
        assert ult_av is not None
        assert ult_av.classificacao_dominio == "EM_DESENVOLVIMENTO"

        # Simulado Adaptativo e Correção
        sim = criar_simulado_adaptativo(
            db=db,
            titulo="Simulado Teste Automatizado",
            banca_estilo="Cebraspe",
            modo_selecao="ADAPTATIVO_PONTOS_FRACOS",
            quantidade_questoes=3,
            tempo_previsto_minutos=30,
        )
        q_ids = json.loads(sim.questoes_ids_json or "[]")
        assert len(q_ids) == 3
        res_sim = corrigir_simulado(
            db, sim.id, {q_ids[0]: "CERTO", q_ids[1]: "ERRADO"}, 20
        )
        assert res_sim.total_questoes == 3

        # Backup Atômico SQLite com integridade e SHA-256
        info_bak = criar_backup_sqlite()
        assert info_bak["integridade"] == "ok"
        assert len(info_bak["sha256"]) == 64
