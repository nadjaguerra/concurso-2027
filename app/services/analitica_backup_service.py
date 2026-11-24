"""Serviços Analíticos (Dashboard, Desempenho, Previsão de Domínio, Simulados, JSON e Backup SQLite)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import (
    BACKUPS_DIR,
    DEFAULT_DB_PATH,
    DISTRIBUICAO_INTERNA_TECNOLOGIA,
    EXPORTS_DIR,
    PESO_EIXO_ANPD_TI,
    PESO_EIXO_SEFAZ_PE,
)
from app.models.entities import (
    AssociacaoTopicoConcurso,
    Concurso,
    Disciplina,
    EntendimentoJurisprudencia,
    ErroCaderno,
    Flashcard,
    HistoricoProvaCobranca,
    Material,
    MetaAlerta,
    NormaJuridica,
    Questao,
    RespostaQuestao,
    ResultadoSimulado,
    Revisao,
    SessaoEstudo,
    SessaoQuestoes,
    Simulado,
    Topico,
)


def calcular_indicadores_dashboard(db: Session) -> dict[str, Any]:
    """Calcula indicadores 100% baseados em dados reais persistidos no SQLite (Seções 6 e 19)."""
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=7)
    inicio_mes = hoje - timedelta(days=30)

    topicos = db.scalars(select(Topico)).all()
    total_topicos = len(topicos)
    topicos_concluidos = sum(
        1 for t in topicos if t.status_estudo in ("ESTUDADO", "EM_REVISAO", "DOMINADO")
    )
    topicos_dominados = sum(1 for t in topicos if t.status_estudo == "DOMINADO")
    topicos_em_andamento = sum(
        1 for t in topicos if t.status_estudo in ("EM_ESTUDO", "ESTUDADO", "EM_REVISAO")
    )
    topicos_pendentes = total_topicos - topicos_concluidos
    progresso_geral = (
        round(topicos_concluidos / total_topicos * 100.0, 1)
        if total_topicos > 0
        else 0.0
    )

    # Progresso por Eixo Estratégico (Eixo 1: SEFAZ-PE 60% / Eixo 2: ANPD + Dados e TI 40%)
    disc_map = {d.id: d for d in db.scalars(select(Disciplina)).all()}
    top_sefaz = [
        t
        for t in topicos
        if disc_map.get(t.disciplina_id)
        and disc_map[t.disciplina_id].eixo_associado in ("EIXO_1_SEFAZ_PE", "AMBOS_COMUM")
    ]
    top_anpd = [
        t
        for t in topicos
        if disc_map.get(t.disciplina_id)
        and disc_map[t.disciplina_id].eixo_associado in ("EIXO_2_ANPD_TI", "AMBOS_COMUM")
    ]

    prog_sefaz = (
        round(
            sum(
                1
                for t in top_sefaz
                if t.status_estudo in ("ESTUDADO", "EM_REVISAO", "DOMINADO")
            )
            / len(top_sefaz)
            * 100.0,
            1,
        )
        if top_sefaz
        else 0.0
    )
    prog_anpd = (
        round(
            sum(
                1
                for t in top_anpd
                if t.status_estudo in ("ESTUDADO", "EM_REVISAO", "DOMINADO")
            )
            / len(top_anpd)
            * 100.0,
            1,
        )
        if top_anpd
        else 0.0
    )

    # Revisões
    rev_hoje = (
        db.scalar(
            select(func.count(Revisao.id)).where(
                Revisao.status_revisao == "PENDENTE", Revisao.data_prevista == hoje
            )
        )
        or 0
    )
    rev_atrasadas = (
        db.scalar(
            select(func.count(Revisao.id)).where(Revisao.status_revisao == "ATRASADA")
        )
        or 0
    )
    rev_concluidas = (
        db.scalar(
            select(func.count(Revisao.id)).where(Revisao.status_revisao == "CONCLUIDA")
        )
        or 0
    )

    # Questões e Taxa de Acertos (Diferencia ausência de dados de zero!)
    respostas_ind = db.scalars(select(RespostaQuestao)).all()
    baterias_q = db.scalars(select(SessaoQuestoes)).all()
    sessoes_estudo = db.scalars(select(SessaoEstudo)).all()

    total_questoes_realizadas = (
        len(respostas_ind)
        + sum(b.total_questoes for b in baterias_q)
        + sum(s.questoes_realizadas for s in sessoes_estudo)
    )
    total_acertos = (
        sum(1 for r in respostas_ind if r.resultado == "CORRETA")
        + sum(b.acertos for b in baterias_q)
        + sum(s.acertos for s in sessoes_estudo)
    )
    taxa_acertos: Optional[float] = (
        round(total_acertos / total_questoes_realizadas * 100.0, 1)
        if total_questoes_realizadas > 0
        else None
    )

    # Tempo de estudo registrado (total, semanal e mensal)
    minutos_totais = sum(s.duracao_minutos for s in sessoes_estudo)
    minutos_semana = sum(
        s.duracao_minutos for s in sessoes_estudo if s.data_sessao >= inicio_semana
    )
    minutos_mes = sum(
        s.duracao_minutos for s in sessoes_estudo if s.data_sessao >= inicio_mes
    )
    minutos_eixo1 = sum(
        s.duracao_minutos
        for s in sessoes_estudo
        if s.eixo_estrategico == "EIXO_1_SEFAZ_PE"
    )
    minutos_eixo2 = sum(
        s.duracao_minutos
        for s in sessoes_estudo
        if s.eixo_estrategico == "EIXO_2_ANPD_TI"
    )

    # Assuntos com maior dificuldade / erros ativos
    erros_ativos = db.scalars(
        select(ErroCaderno)
        .where(ErroCaderno.status_superacao != "SUPERADO")
        .order_by(ErroCaderno.reincidencias.desc(), ErroCaderno.id.desc())
    ).all()

    # Contagens do acervo e biblioteca
    total_materiais = db.scalar(select(func.count(Material.id))) or 0
    total_normas = db.scalar(select(func.count(NormaJuridica.id))) or 0
    total_juris = db.scalar(select(func.count(EntendimentoJurisprudencia.id))) or 0
    total_flashcards = db.scalar(select(func.count(Flashcard.id))) or 0

    metas_alertas = db.scalars(
        select(MetaAlerta).where(MetaAlerta.ativo == True).order_by(MetaAlerta.id.asc())  # noqa: E712
    ).all()

    return {
        "total_topicos": total_topicos,
        "topicos_concluidos": topicos_concluidos,
        "topicos_dominados": topicos_dominados,
        "topicos_em_andamento": topicos_em_andamento,
        "topicos_pendentes": topicos_pendentes,
        "progresso_geral": progresso_geral,
        "progresso_sefaz_pe": prog_sefaz,
        "progresso_anpd_ti": prog_anpd,
        "peso_meta_sefaz": PESO_EIXO_SEFAZ_PE,
        "peso_meta_anpd_ti": PESO_EIXO_ANPD_TI,
        "distribuicao_interna_tecnologia": DISTRIBUICAO_INTERNA_TECNOLOGIA,
        "revisoes_hoje": rev_hoje,
        "revisoes_atrasadas": rev_atrasadas,
        "revisoes_concluidas": rev_concluidas,
        "total_questoes_realizadas": total_questoes_realizadas,
        "total_acertos": total_acertos,
        "taxa_acertos": taxa_acertos,
        "minutos_totais": minutos_totais,
        "horas_totais": round(minutos_totais / 60.0, 1),
        "minutos_semana": minutos_semana,
        "minutos_mes": minutos_mes,
        "minutos_eixo1": minutos_eixo1,
        "minutos_eixo2": minutos_eixo2,
        "erros_ativos": erros_ativos,
        "total_materiais": total_materiais,
        "total_normas": total_normas,
        "total_juris": total_juris,
        "total_flashcards": total_flashcards,
        "metas_alertas": metas_alertas,
    }


def calcular_previsao_dominio_por_disciplina(db: Session) -> list[dict[str, Any]]:
    """Calcula desempenho e estimativa de domínio por disciplina com critérios explícitos (Seção 19)."""
    disciplinas = db.scalars(
        select(Disciplina).order_by(Disciplina.ordem_exibicao.asc())
    ).all()
    relatorio: list[dict[str, Any]] = []

    for d in disciplinas:
        sessoes = db.scalars(
            select(SessaoEstudo).where(SessaoEstudo.disciplina_id == d.id)
        ).all()
        respostas = db.scalars(
            select(RespostaQuestao).where(RespostaQuestao.disciplina_id == d.id)
        ).all()
        baterias = db.scalars(
            select(SessaoQuestoes).where(SessaoQuestoes.disciplina_id == d.id)
        ).all()
        erros_d = (
            db.scalar(
                select(func.count(ErroCaderno.id)).where(
                    ErroCaderno.disciplina_id == d.id,
                    ErroCaderno.status_superacao != "SUPERADO",
                )
            )
            or 0
        )

        minutos = sum(s.duracao_minutos for s in sessoes)
        q_total = (
            len(respostas)
            + sum(b.total_questoes for b in baterias)
            + sum(s.questoes_realizadas for s in sessoes)
        )
        q_acertos = (
            sum(1 for r in respostas if r.resultado == "CORRETA")
            + sum(b.acertos for b in baterias)
            + sum(s.acertos for s in sessoes)
        )
        taxa = round(q_acertos / q_total * 100.0, 1) if q_total > 0 else None

        # Regra 27: Quando não houver dados suficientes, não produzir estimativa artificial!
        if q_total < 5 and minutos < 30:
            dominio_estimado = "Dados insuficientes para estimativa (requer >= 5 questões ou >= 30 min registrados)"
            recomendacao = "Iniciar estudo teórico/legislação e registrar primeira bateria diagnóstica."
        elif taxa is not None and taxa >= 80.0 and q_total >= 15 and erros_d == 0:
            dominio_estimado = "Consolidado (Baseado em >= 15 questões e >= 80% de acerto)"
            recomendacao = "Manter em ciclo de revisão espaçada D15/D30/D60 e simulados."
        elif taxa is not None and taxa >= 65.0:
            dominio_estimado = "Intermediário / Em Evolução"
            recomendacao = "Reforçar subassuntos com erros registrados e avançar para a meta de 20 questões/tópico."
        else:
            dominio_estimado = "Inicial / Atenção Prioritária"
            recomendacao = "Priorizar leitura da legislação oficial do acervo e revisão D1/D7 dos pontos vulneráveis."

        relatorio.append(
            {
                "disciplina": d,
                "minutos_estudados": minutos,
                "questoes_resolvidas": q_total,
                "acertos": q_acertos,
                "taxa_acerto": taxa,
                "erros_ativos": erros_d,
                "dominio_estimado": dominio_estimado,
                "recomendacao_justificada": recomendacao,
            }
        )
    return relatorio


def criar_simulado_adaptativo(
    db: Session,
    titulo: str,
    banca_estilo: str,
    modo_selecao: str,
    quantidade_questoes: int,
    tempo_previsto_minutos: int,
    disciplina_ids: Optional[list[int]] = None,
) -> Simulado:
    """Monta um simulado priorizando tópicos com erros ou menor domínio quando em modo adaptativo (Seção 18)."""
    stmt = select(Questao)
    if disciplina_ids:
        stmt = stmt.where(Questao.disciplina_id.in_(disciplina_ids))
    questoes_disp = list(db.scalars(stmt).all())

    if modo_selecao == "ADAPTATIVO_PONTOS_FRACOS":
        # Pontua cada questão pela quantidade de erros ativos em seu tópico/disciplina
        erros_por_topico: dict[int, int] = {}
        for e in db.scalars(
            select(ErroCaderno).where(ErroCaderno.status_superacao != "SUPERADO")
        ).all():
            if e.topico_id:
                erros_por_topico[e.topico_id] = (
                    erros_por_topico.get(e.topico_id, 0) + e.reincidencias
                )
        questoes_disp.sort(
            key=lambda q: erros_por_topico.get(q.topico_id or -1, 0), reverse=True
        )

    selecionadas = questoes_disp[: max(1, min(quantidade_questoes, len(questoes_disp)))]
    q_ids = [q.id for q in selecionadas]

    sim = Simulado(
        titulo=titulo,
        banca_estilo=banca_estilo,
        modo_selecao=modo_selecao,
        quantidade_questoes=len(q_ids),
        tempo_previsto_minutos=tempo_previsto_minutos,
        disciplinas_selecionadas_json=json.dumps(disciplina_ids or []),
        questoes_ids_json=json.dumps(q_ids),
        status_simulado="EM_ANDAMENTO",
        data_realizacao=date.today(),
    )
    db.add(sim)
    db.commit()
    db.refresh(sim)
    return sim


def corrigir_simulado(
    db: Session,
    simulado_id: int,
    respostas_map: dict[int, str],
    tempo_gasto_minutos: int,
) -> ResultadoSimulado:
    """Corrige um simulado, calcula escore líquido Cebraspe e alimenta o Caderno de Erros."""
    sim = db.get(Simulado, simulado_id)
    if not sim:
        raise ValueError("Simulado não encontrado.")

    q_ids = json.loads(sim.questoes_ids_json or "[]")
    acertos = 0
    erros = 0
    em_branco = 0
    pontos_fracos: list[str] = []
    por_disc: dict[str, dict[str, int]] = {}

    for qid in q_ids:
        q = db.get(Questao, qid)
        if not q:
            continue
        disc = db.get(Disciplina, q.disciplina_id)
        dnome = disc.nome if disc else "Geral"
        por_disc.setdefault(dnome, {"total": 0, "acertos": 0, "erros": 0})
        por_disc[dnome]["total"] += 1

        resp_usr = (respostas_map.get(qid) or "").strip().upper()
        gab = q.gabarito.strip().upper()

        if not resp_usr or resp_usr == "BRANCO":
            em_branco += 1
            res_status = "EM_BRANCO"
        elif resp_usr == gab:
            acertos += 1
            por_disc[dnome]["acertos"] += 1
            res_status = "CORRETA"
        else:
            erros += 1
            por_disc[dnome]["erros"] += 1
            res_status = "INCORRETA"
            pontos_fracos.append(f"{dnome}: Questão #{q.id} ({q.concurso_referencia})")

        resp_obj = RespostaQuestao(
            questao_id=q.id,
            simulado_id=sim.id,
            disciplina_id=q.disciplina_id,
            topico_id=q.topico_id,
            banca_nome=q.banca_nome,
            concurso_nome=q.concurso_referencia,
            data_resolucao=date.today(),
            resposta_escolhida=resp_usr or "EM_BRANCO",
            gabarito_correto=gab,
            resultado=res_status,
            confianca="SABIA" if res_status == "CORRETA" else "DUVIDA",
            pendente_revisao=(res_status != "CORRETA"),
        )
        db.add(resp_obj)
        db.flush()

        if res_status == "INCORRETA":
            db.add(
                ErroCaderno(
                    resposta_questao_id=resp_obj.id,
                    questao_id=q.id,
                    referencia_questao_externa=f"Simulado '{sim.titulo}' — Questão #{q.id} ({q.concurso_referencia})",
                    disciplina_id=q.disciplina_id,
                    topico_id=q.topico_id,
                    categoria_erro="FALTA_CONHECIMENTO",
                    alternativa_escolhida=resp_usr,
                    resposta_correta=gab,
                    explicacao_correcao=q.comentario_explicacao
                    or "Revisar fundamentação normativa e jurisprudencial do item.",
                    plano_acao="Reforçar tópico na Etapa 1 de Revisões do Meu Dia.",
                    data_erro=date.today(),
                    proxima_revisao_em=date.today() + timedelta(days=1),
                )
            )

    total_q = max(1, len(q_ids))
    perc = round(acertos / total_q * 100.0, 1)
    liquida_cebraspe = float(acertos - erros)

    sim.status_simulado = "CONCLUIDO"
    resultado = db.scalar(
        select(ResultadoSimulado).where(ResultadoSimulado.simulado_id == sim.id)
    )
    if not resultado:
        resultado = ResultadoSimulado(
            simulado_id=sim.id,
            tempo_gasto_minutos=tempo_gasto_minutos,
            total_questoes=len(q_ids),
            acertos=acertos,
            erros=erros,
            em_branco=em_branco,
            pontuacao_liquida_cebraspe=liquida_cebraspe,
            percentual_acerto=perc,
            pontos_fracos_identificados_json=json.dumps(
                pontos_fracos, ensure_ascii=False
            ),
            desempenho_por_disciplina_json=json.dumps(por_disc, ensure_ascii=False),
        )
        db.add(resultado)
    db.commit()
    db.refresh(resultado)
    return resultado


def exportar_jurisprudencia_json(db: Session) -> dict[str, Any]:
    """Exporta toda a biblioteca de Jurisprudência, Súmulas e progresso SM-2 em formato JSON (Seções 20 e 24)."""
    registros = db.scalars(
        select(EntendimentoJurisprudencia).order_by(EntendimentoJurisprudencia.id.asc())
    ).all()
    items = []
    for r in registros:
        items.append(
            {
                "tribunal": r.tribunal,
                "tipo_entendimento": r.tipo_entendimento,
                "numero_identificacao": r.numero_identificacao,
                "assunto_titulo": r.assunto_titulo,
                "texto_entendimento": r.texto_entendimento,
                "resumo_didatico": r.resumo_didatico,
                "data_publicacao": r.data_publicacao.isoformat()
                if r.data_publicacao
                else None,
                "situacao_vigencia": r.situacao_vigencia,
                "fonte_oficial": r.fonte_oficial,
                "link_origem": r.link_origem,
                "concursos_relacionados": r.concursos_relacionados,
                "favorito": r.favorito,
                "anotacoes_pessoais": r.anotacoes_pessoais,
                "sm2_repeticoes": r.sm2_repeticoes,
                "sm2_easiness_factor": r.sm2_easiness_factor,
                "sm2_intervalo_dias": r.sm2_intervalo_dias,
                "estimativa_dominio": r.estimativa_dominio,
            }
        )
    payload = {
        "plataforma": "Plataforma Concurso 2027",
        "modulo": "Jurisprudência, Súmulas e Informativos (SM-2)",
        "exportado_em": datetime.now().isoformat(),
        "total_registros": len(items),
        "entendimentos": items,
    }
    out_file = (
        EXPORTS_DIR
        / f"jurisprudencia_sumulas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    out_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return payload


def importar_jurisprudencia_json(
    db: Session, payload: dict[str, Any], sobrescrever_duplicados: bool = False
) -> dict[str, int]:
    """Importa JSON de Jurisprudência/Súmulas com prevenção de duplicidades (Seção 24)."""
    lista = payload.get("entendimentos") or []
    inseridos = 0
    ignorados_duplicados = 0
    atualizados = 0

    for item in lista:
        trib = (item.get("tribunal") or "").strip()
        num = (item.get("numero_identificacao") or "").strip()
        texto = (item.get("texto_entendimento") or "").strip()
        if not trib or not num or not texto:
            continue

        existente = db.scalar(
            select(EntendimentoJurisprudencia).where(
                EntendimentoJurisprudencia.tribunal == trib,
                EntendimentoJurisprudencia.numero_identificacao == num,
            )
        )
        if existente:
            if sobrescrever_duplicados:
                existente.assunto_titulo = (
                    item.get("assunto_titulo") or existente.assunto_titulo
                )
                existente.texto_entendimento = texto
                existente.resumo_didatico = (
                    item.get("resumo_didatico") or existente.resumo_didatico
                )
                existente.fonte_oficial = (
                    item.get("fonte_oficial") or existente.fonte_oficial
                )
                atualizados += 1
            else:
                ignorados_duplicados += 1
            continue

        db.add(
            EntendimentoJurisprudencia(
                tribunal=trib,
                tipo_entendimento=item.get("tipo_entendimento") or "SUMULA_STF",
                numero_identificacao=num,
                assunto_titulo=item.get("assunto_titulo") or num,
                texto_entendimento=texto,
                resumo_didatico=item.get("resumo_didatico"),
                situacao_vigencia=item.get("situacao_vigencia") or "VIGENTE_VERIFICADA",
                fonte_oficial=item.get("fonte_oficial")
                or "Importação JSON Verificada",
                link_origem=item.get("link_origem"),
                concursos_relacionados=item.get("concursos_relacionados")
                or "SEFAZ-PE, ANPD",
                favorito=bool(item.get("favorito", False)),
                anotacoes_pessoais=item.get("anotacoes_pessoais"),
                sm2_proxima_revisao=date.today(),
            )
        )
        inseridos += 1

    db.commit()
    return {
        "inseridos": inseridos,
        "atualizados": atualizados,
        "ignorados_duplicados": ignorados_duplicados,
    }


def criar_backup_sqlite(db_path: Optional[Path] = None) -> dict[str, Any]:
    """Cria um backup atômico online do banco SQLite com verificação de integridade e hash SHA-256."""
    origem = db_path or DEFAULT_DB_PATH
    if not origem.exists():
        raise FileNotFoundError(f"Banco SQLite não encontrado em {origem}")

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = BACKUPS_DIR / f"plataforma2027_backup_{carimbo}.sqlite3"

    src_conn = sqlite3.connect(str(origem))
    dst_conn = sqlite3.connect(str(destino))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
        cur = dst_conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        integridade = cur.fetchone()[0]
    finally:
        dst_conn.close()
        src_conn.close()

    h = hashlib.sha256()
    with destino.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    sha = h.hexdigest()

    manifesto = destino.with_suffix(".sqlite3.sha256")
    manifesto.write_text(
        f"{sha}  {destino.name}\nIntegridade SQLite: {integridade}\nData: {datetime.now().isoformat()}\n",
        encoding="utf-8",
    )

    return {
        "arquivo_backup": destino.name,
        "caminho_backup": str(destino),
        "tamanho_bytes": destino.stat().st_size,
        "sha256": sha,
        "integridade": integridade,
    }
