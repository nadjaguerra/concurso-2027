"""Motor de Planejamento Inteligente, Meu Dia (4 Etapas), Revisões D1-D60 e SM-2 (Etapas 7, 9 e 10)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import PESO_EIXO_ANPD_TI, PESO_EIXO_SEFAZ_PE
from app.models.entities import (
    AssociacaoTopicoConcurso,
    Concurso,
    Configuracao,
    Disciplina,
    EntendimentoJurisprudencia,
    ErroCaderno,
    Flashcard,
    RespostaQuestao,
    Revisao,
    SessaoEstudo,
    TarefaCronograma,
    Topico,
)

MAPA_CICLOS_GERAL: list[tuple[str, int]] = [
    ("D1", 1),
    ("D7", 7),
    ("D15", 15),
    ("D30", 30),
    ("D60", 60),
]


def atualizar_status_revisoes_vencidas(db: Session, hoje: Optional[date] = None) -> int:
    """Marca revisões pendentes com data anterior a hoje como ATRASADA (nunca concluída automaticamente)."""
    ref = hoje or date.today()
    vencidas = db.scalars(
        select(Revisao).where(
            Revisao.status_revisao == "PENDENTE", Revisao.data_prevista < ref
        )
    ).all()
    for r in vencidas:
        r.status_revisao = "ATRASADA"
    if vencidas:
        db.commit()
    return len(vencidas)


def proximo_ciclo_revisao_geral(
    ciclo_atual: str,
    dificuldade: int,
    confianca: str,
    percentual_acerto: Optional[float],
    tem_erro_reincidente: bool,
) -> tuple[str, int]:
    """Calcula o próximo ciclo e intervalo adaptativo dentro da escada D1 -> D7 -> D15 -> D30 -> D60."""
    ordem = ["D1", "D7", "D15", "D30", "D60"]
    base_dias = {"D1": 1, "D7": 7, "D15": 15, "D30": 30, "D60": 60}
    idx = ordem.index(ciclo_atual) if ciclo_atual in ordem else 0

    baixo_desempenho = (
        dificuldade >= 4
        or confianca == "BAIXA"
        or (percentual_acerto is not None and percentual_acerto < 65.0)
        or tem_erro_reincidente
    )

    if baixo_desempenho:
        # Mantém ou recua um degrau e reduz o intervalo para reforço imediato
        novo_idx = max(0, idx)
        prox_ciclo = ordem[novo_idx]
        intervalo = max(1, int(round(base_dias[prox_ciclo] * 0.6)))
        return prox_ciclo, intervalo

    # Avança um degrau na escada D1 -> D7 -> D15 -> D30 -> D60
    novo_idx = min(len(ordem) - 1, idx + 1)
    prox_ciclo = ordem[novo_idx]
    intervalo = base_dias[prox_ciclo]
    if dificuldade <= 2 and confianca == "ALTA" and (percentual_acerto or 85.0) >= 85.0:
        intervalo = int(round(intervalo * 1.15))
    return prox_ciclo, intervalo


def concluir_revisao_geral(
    db: Session,
    revisao_id: int,
    duracao_minutos: int,
    dificuldade: int,
    confianca: str,
    questoes_feitas: int = 0,
    acertos: int = 0,
    autoavaliacao: str = "",
    data_execucao: Optional[date] = None,
) -> Revisao:
    """Conclui manualmente uma revisão geral e agenda a próxima revisão adaptativa."""
    ref = data_execucao or date.today()
    rev = db.get(Revisao, revisao_id)
    if not rev:
        raise ValueError("Revisão não encontrada.")

    perc = (acertos / questoes_feitas * 100.0) if questoes_feitas > 0 else None
    rev.data_realizada = ref
    rev.status_revisao = "CONCLUIDA"
    rev.dificuldade_na_revisao = dificuldade
    rev.confianca_na_revisao = confianca
    rev.percentual_acerto_revisao = perc
    rev.autoavaliacao = autoavaliacao

    # Atualiza tarefa do Meu Dia correspondente, se existir
    tarefas_rev = db.scalars(
        select(TarefaCronograma).where(
            TarefaCronograma.revisao_id == rev.id,
            TarefaCronograma.status_tarefa != "CONCLUIDA",
        )
    ).all()
    for tr in tarefas_rev:
        tr.status_tarefa = "CONCLUIDA"
        tr.duracao_realizada_minutos = duracao_minutos

    # Verifica se há erros reincidentes ativos no tópico
    erros_ativos = db.scalar(
        select(func.count(ErroCaderno.id)).where(
            ErroCaderno.topico_id == rev.topico_id,
            ErroCaderno.status_superacao != "SUPERADO",
        )
    ) or 0

    prox_ciclo, prox_intervalo = proximo_ciclo_revisao_geral(
        rev.ciclo_revisao,
        dificuldade,
        confianca,
        perc,
        erros_ativos > 0,
    )

    nova_rev = Revisao(
        topico_id=rev.topico_id,
        disciplina_id=rev.disciplina_id,
        ciclo_revisao=prox_ciclo,
        modalidade_revisao="Recuperação Ativa + Questões + Legislação",
        intervalo_dias_aplicado=prox_intervalo,
        data_prevista=ref + timedelta(days=prox_intervalo),
        status_revisao="PENDENTE",
    )
    db.add(nova_rev)

    # Registra sessão de estudo correspondente
    disc = db.get(Disciplina, rev.disciplina_id)
    eixo = (
        "EIXO_2_ANPD_TI"
        if disc and disc.eixo_associado == "EIXO_2_ANPD_TI"
        else "EIXO_1_SEFAZ_PE"
    )
    sessao = SessaoEstudo(
        data_sessao=ref,
        duracao_minutos=max(5, duracao_minutos),
        tipo_sessao="REVISAO",
        status_execucao="CONCLUIDA",
        eixo_estrategico=eixo,
        disciplina_id=rev.disciplina_id,
        topico_id=rev.topico_id,
        revisao_id=rev.id,
        questoes_realizadas=questoes_feitas,
        acertos=acertos,
        erros=max(0, questoes_feitas - acertos),
        dificuldade_percebida=dificuldade,
        grau_compreensao="BOM" if (perc is None or perc >= 70) else "REGULAR",
        nivel_confianca=confianca,
        observacoes=f"Revisão {rev.ciclo_revisao} concluída. Próxima ({prox_ciclo}) agendada para +{prox_intervalo} dia(s). {autoavaliacao}".strip(),
    )
    db.add(sessao)

    # Atualiza status do tópico com base em evidências reais
    topico = db.get(Topico, rev.topico_id)
    if topico:
        _atualizar_dominio_topico_baseado_em_evidencias(db, topico)

    db.commit()
    db.refresh(rev)
    return rev


def calcular_sm2(
    qualidade_0_a_5: int,
    repeticoes_atuais: int,
    ef_atual: float,
    intervalo_atual: int,
) -> tuple[int, float, int]:
    """Algoritmo oficial SM-2 (SuperMemo 2) utilizado exclusivamente para Flashcards e Jurisprudência/Súmulas.

    Retorna: (novas_repeticoes, novo_easiness_factor, novo_intervalo_dias)
    """
    q = max(0, min(5, int(qualidade_0_a_5)))
    if q < 3:
        novas_rep = 0
        novo_int = 1
    else:
        if repeticoes_atuais == 0:
            novo_int = 1
        elif repeticoes_atuais == 1:
            novo_int = 6
        else:
            novo_int = max(1, int(round(intervalo_atual * ef_atual)))
        novas_rep = repeticoes_atuais + 1

    novo_ef = ef_atual + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    novo_ef = max(1.3, round(novo_ef, 3))
    return novas_rep, novo_ef, novo_int


def avaliar_entendimento_sm2(
    db: Session,
    juris_id: int,
    qualidade_0_a_5: int,
    compreensao: str = "",
    dificuldade: int = 3,
    data_ref: Optional[date] = None,
) -> EntendimentoJurisprudencia:
    """Aplica o algoritmo SM-2 a um entendimento de Jurisprudência/Súmula e agenda a próxima revisão."""
    hoje = data_ref or date.today()
    ent = db.get(EntendimentoJurisprudencia, juris_id)
    if not ent:
        raise ValueError("Entendimento de jurisprudência/súmula não encontrado.")

    rep, ef, interv = calcular_sm2(
        qualidade_0_a_5,
        ent.sm2_repeticoes,
        ent.sm2_easiness_factor,
        ent.sm2_intervalo_dias,
    )
    ent.sm2_repeticoes = rep
    ent.sm2_easiness_factor = ef
    ent.sm2_intervalo_dias = interv
    ent.sm2_ultima_revisao = hoje
    ent.sm2_proxima_revisao = hoje + timedelta(days=interv)
    ent.dificuldade_percebida = dificuldade
    if compreensao:
        ent.compreensao_registrada = compreensao

    if qualidade_0_a_5 >= 3:
        ent.total_acertos += 1
    else:
        ent.total_erros += 1

    if rep >= 4 and ef >= 2.3 and ent.total_acertos >= 3:
        ent.estimativa_dominio = "CONSOLIDADO"
    elif rep >= 2:
        ent.estimativa_dominio = "INTERMEDIARIO"
    else:
        ent.estimativa_dominio = "INICIAL"

    hist = json.loads(ent.historico_estudo_json or "[]")
    hist.append(
        {
            "data": hoje.isoformat(),
            "qualidade_sm2": qualidade_0_a_5,
            "intervalo_gerado": interv,
            "ef": ef,
            "compreensao": compreensao,
        }
    )
    ent.historico_estudo_json = json.dumps(hist[-20:], ensure_ascii=False)

    # Marca tarefa Etapa 3 do Meu Dia como concluída, se houver
    tarefas_j = db.scalars(
        select(TarefaCronograma).where(
            TarefaCronograma.jurisprudencia_id == ent.id,
            TarefaCronograma.data_programada == hoje,
        )
    ).all()
    for tj in tarefas_j:
        tj.status_tarefa = "CONCLUIDA"
        tj.duracao_realizada_minutos = 15

    db.commit()
    db.refresh(ent)
    return ent


def avaliar_flashcard_sm2(
    db: Session,
    flashcard_id: int,
    qualidade_0_a_5: int,
    data_ref: Optional[date] = None,
) -> Flashcard:
    """Aplica o algoritmo SM-2 a um Flashcard e atualiza seu histórico."""
    hoje = data_ref or date.today()
    card = db.get(Flashcard, flashcard_id)
    if not card:
        raise ValueError("Flashcard não encontrado.")

    rep, ef, interv = calcular_sm2(
        qualidade_0_a_5,
        card.sm2_repeticoes,
        card.sm2_easiness_factor,
        card.sm2_intervalo_dias,
    )
    card.sm2_repeticoes = rep
    card.sm2_easiness_factor = ef
    card.sm2_intervalo_dias = interv
    card.ultima_revisao_em = hoje
    card.proxima_revisao_em = hoje + timedelta(days=interv)
    card.total_revisoes += 1

    if rep >= 4 and ef >= 2.3:
        card.dominio_avaliado = "CONSOLIDADO"
    elif rep >= 2:
        card.dominio_avaliado = "INTERMEDIARIO"
    else:
        card.dominio_avaliado = "EM_APRENDIZADO"

    hist = json.loads(card.historico_json or "[]")
    hist.append(
        {
            "data": hoje.isoformat(),
            "qualidade_sm2": qualidade_0_a_5,
            "intervalo_dias": interv,
            "ef": ef,
        }
    )
    card.historico_json = json.dumps(hist[-20:], ensure_ascii=False)
    db.commit()
    db.refresh(card)
    return card


def _atualizar_dominio_topico_baseado_em_evidencias(
    db: Session, topico: Topico
) -> None:
    """Regra 9, 11 e 27.10: Não marcar conteúdo como dominado sem evidências históricas e de questões."""
    total_sessoes = (
        db.scalar(
            select(func.count(SessaoEstudo.id)).where(
                SessaoEstudo.topico_id == topico.id,
                SessaoEstudo.status_execucao == "CONCLUIDA",
            )
        )
        or 0
    )
    respostas = db.scalars(
        select(RespostaQuestao).where(RespostaQuestao.topico_id == topico.id)
    ).all()
    sessoes_q = db.scalars(
        select(SessaoEstudo).where(
            SessaoEstudo.topico_id == topico.id,
            SessaoEstudo.questoes_realizadas > 0,
        )
    ).all()

    total_q = len(respostas) + sum(s.questoes_realizadas for s in sessoes_q)
    acertos_q = sum(1 for r in respostas if r.resultado == "CORRETA") + sum(
        s.acertos for s in sessoes_q
    )
    taxa_acerto = (acertos_q / total_q * 100.0) if total_q > 0 else 0.0

    erros_pendentes = (
        db.scalar(
            select(func.count(ErroCaderno.id)).where(
                ErroCaderno.topico_id == topico.id,
                ErroCaderno.status_superacao != "SUPERADO",
            )
        )
        or 0
    )

    if total_sessoes >= 2 and total_q >= 10 and taxa_acerto >= 80.0 and erros_pendentes == 0:
        topico.status_estudo = "DOMINADO"
        topico.situacao_dominio = "CONSOLIDADO"
    elif total_sessoes >= 1 and total_q >= 5 and taxa_acerto >= 70.0:
        topico.status_estudo = "EM_REVISAO"
        topico.situacao_dominio = "BOM"
    elif total_sessoes >= 1:
        topico.status_estudo = "ESTUDADO"
        topico.situacao_dominio = "EM_DESENVOLVIMENTO"


TRILHA_SEMANAS: list[tuple[int, str, list[str]]] = [
    (1, "Constitucional + Raciocínio Lógico", ["DIR_CONST", "RLM"]),
    (2, "Constitucional + Raciocínio Lógico", ["DIR_CONST", "RLM"]),
    (3, "Direito Administrativo + Adm. Geral e Pública", ["DIR_ADM", "ADM_PUB"]),
    (4, "Direito Administrativo + Adm. Geral e Pública", ["DIR_ADM", "ADM_PUB"]),
    (5, "Administração Geral e Pública (20 questões)", ["ADM_PUB", "GEST_PESS_MAT"]),
    (6, "Administração Pública + Orçamento Público", ["ADM_PUB", "AFO"]),
    (7, "Educação Fiscal, Informática e Leis de PE", ["EDU_FISCAL", "INFO_BASICA", "LEG_PE"]),
    (8, "Revisão geral e simulados", ["DIR_CONST", "DIR_ADM", "ADM_PUB", "RLM"]),
]

FASES_MANUAIS: dict[str, tuple[str, list[str]]] = {
    "FASE_1_BASE_SOLIDA": ("Base sólida", ["DIR_CONST", "DIR_ADM", "RLM"]),
    "FASE_2_FECHAMENTO_SEFAZ": (
        "Fechar SEFAZ-PE",
        ["ADM_PUB", "AFO", "LEG_PE", "GEST_PESS_MAT", "EDU_FISCAL", "INFO_BASICA"],
    ),
    "FASE_3_ACELERACAO_ANPD": (
        "Acelerar ANPD (Dados & TI)",
        ["LGPD_ANPD", "TI_CD_EST", "TI_ENG_DADOS", "TI_IA"],
    ),
}

# Distribuição oficial de questões — Edital SEFAZ-PE nº 001/2022, item 5.2.1
PESO_PROVA_SEFAZ_2022: list[tuple[str, int]] = [
    ("Administração Geral e Pública", 20),
    ("Língua Portuguesa", 10),
    ("Raciocínio Lógico-Matemático", 5),
    ("Informática", 5),
    ("Direito Administrativo", 5),
    ("Direito Constitucional", 5),
    ("Orçamento Público", 5),
    ("Educação Fiscal", 5),
]


def obter_contexto_trilha_60d(db: Session, hoje: Optional[date] = None) -> dict[str, Any]:
    """Plano de 8 semanas (60 dias) para fechar o edital da SEFAZ-PE, calculado pela data."""
    ref = hoje or date.today()

    def _cfg(chave: str):
        return db.scalar(select(Configuracao).where(Configuracao.chave == chave))

    cfg_modo = _cfg("modo_trilha")
    cfg_inicio = _cfg("inicio_ciclo_sefaz_60d")
    cfg_prazo = _cfg("prazo_dias_sefaz")
    cfg_inicio_anpd = _cfg("inicio_ciclo_anpd_120d")
    cfg_prazo_anpd = _cfg("prazo_dias_anpd")

    modo = json.loads(cfg_modo.valor_json) if cfg_modo else "AUTO"
    try:
        inicio = date.fromisoformat(json.loads(cfg_inicio.valor_json)) if cfg_inicio else ref
    except Exception:
        inicio = ref
    prazo = int(json.loads(cfg_prazo.valor_json)) if cfg_prazo else 60
    try:
        inicio_anpd = date.fromisoformat(json.loads(cfg_inicio_anpd.valor_json)) if cfg_inicio_anpd else inicio
    except Exception:
        inicio_anpd = inicio
    prazo_anpd = int(json.loads(cfg_prazo_anpd.valor_json)) if cfg_prazo_anpd else 120

    dia_atual = max(1, (ref - inicio).days + 1)
    dia_anpd = max(1, (ref - inicio_anpd).days + 1)

    semana: Optional[int] = None
    if modo in FASES_MANUAIS:
        fase = modo
        foco, codigos = FASES_MANUAIS[modo]
    elif dia_atual > prazo:
        fase = "FASE_3_ACELERACAO_ANPD"
        foco, codigos = FASES_MANUAIS[fase]
    else:
        semana = min(8, (dia_atual - 1) // 7 + 1)
        _, foco, codigos = TRILHA_SEMANAS[semana - 1]
        fase = "FASE_1_BASE_SOLIDA" if semana <= 4 else "FASE_2_FECHAMENTO_SEFAZ"

    roadmap = []
    for num, titulo, _ in TRILHA_SEMANAS:
        if semana is not None:
            estado = "atual" if num == semana else ("feito" if num < semana else "futuro")
        else:
            estado = "feito" if dia_atual > prazo else "futuro"
        roadmap.append({"semana": num, "titulo": titulo, "estado": estado})

    return {
        "modo": modo,
        "fase_codigo": fase,
        "fase_titulo": foco,
        "semana": semana,
        "foco_semana": foco,
        "codigos_materia": codigos,
        "roadmap": roadmap,
        "dia_atual": dia_atual,
        "prazo_dias": prazo,
        "dias_restantes": max(0, prazo - dia_atual),
        "perc_tempo": min(100, int(round(dia_atual / max(1, prazo) * 100))),
        "anpd_hoje": ref.weekday() in (1, 3, 5),
        "anpd_dia_atual": dia_anpd,
        "anpd_prazo_dias": prazo_anpd,
    }


def alterar_fase_estudo(db: Session, nova_fase: str) -> None:
    """Fixa uma fase manualmente (ou volta para AUTO) e reorganiza as metas pendentes de hoje."""
    if nova_fase != "AUTO" and nova_fase not in FASES_MANUAIS:
        return
    cfg = db.scalar(select(Configuracao).where(Configuracao.chave == "modo_trilha"))
    if cfg:
        cfg.valor_json = json.dumps(nova_fase)
    else:
        db.add(
            Configuracao(
                chave="modo_trilha",
                valor_json=json.dumps(nova_fase),
                categoria="ESTRATEGIA",
                descricao="AUTO ou fase fixa",
            )
        )
    db.commit()
    gerar_ou_obter_meu_dia(db, forcar_reorganizacao=True)


def gerar_ou_obter_meu_dia(
    db: Session, data_alvo: Optional[date] = None, forcar_reorganizacao: bool = False
) -> dict[str, Any]:
    """Gera ou recupera a sequência diária refinada:

    - ETAPA 1: Revisões (D1/D7/D15/D30/D60 vencidas ou do dia).
    - ETAPA 2: Português TODO DIA + 1 Matéria Principal conforme a Fase (Base Sólida primeiro:
               RLM, Dir. Constitucional, Dir. Administrativo -> depois AFO/Adm. Pública/Leis PE)
               + 1 dose tranquila de ANPD (foco Dados & TI / Cebraspe).
    - ETAPA 3: Uma Jurisprudência ou Súmula do dia (10 min, SM-2).
    - ETAPA 4: Registro do Aprendizado.
    """
    hoje = data_alvo or date.today()
    atualizar_status_revisoes_vencidas(db, hoje)
    trilha = obter_contexto_trilha_60d(db, hoje)

    if forcar_reorganizacao:
        pendentes_hoje = db.scalars(
            select(TarefaCronograma).where(
                TarefaCronograma.data_programada == hoje,
                TarefaCronograma.status_tarefa == "PENDENTE",
            )
        ).all()
        for p in pendentes_hoje:
            db.delete(p)
        db.commit()

    tarefas_existentes = db.scalars(
        select(TarefaCronograma)
        .where(
            TarefaCronograma.data_programada == hoje,
            TarefaCronograma.status_tarefa != "TRANSFERIDA",
        )
        .order_by(TarefaCronograma.etapa_meu_dia, TarefaCronograma.ordem_no_dia)
    ).all()

    if not tarefas_existentes:
        ordem_seq = 1
        disciplinas_do_dia_ids: list[int] = []
        disc_by_cod = {
            d.codigo: d for d in db.scalars(select(Disciplina)).all()
        }

        # =====================================================================
        # ETAPA 1 — REVISÕES (SEMPRE EM PRIMEIRO LUGAR)
        # =====================================================================
        revisoes_devidas = db.scalars(
            select(Revisao)
            .where(
                Revisao.status_revisao.in_(["ATRASADA", "PENDENTE"]),
                Revisao.data_prevista <= hoje,
            )
            .order_by(Revisao.data_prevista.asc())
        ).all()

        for rev in revisoes_devidas[:4]:
            top = db.get(Topico, rev.topico_id)
            disc = db.get(Disciplina, rev.disciplina_id)
            if not top or not disc:
                continue
            disciplinas_do_dia_ids.append(disc.id)
            dur_rev = 25 if rev.ciclo_revisao in ("D1", "D7") else 20
            eixo_rev = (
                "EIXO_2_ANPD_TI"
                if disc.eixo_associado == "EIXO_2_ANPD_TI"
                else "EIXO_1_SEFAZ_PE"
            )
            db.add(
                TarefaCronograma(
                    data_programada=hoje,
                    etapa_meu_dia=1,
                    nome_etapa="Revisão",
                    ordem_no_dia=ordem_seq,
                    eixo_estrategico=eixo_rev,
                    disciplina_id=disc.id,
                    topico_id=top.id,
                    revisao_id=rev.id,
                    titulo_tarefa=f"Revisão {rev.ciclo_revisao} • {disc.nome}: {top.titulo}",
                    duracao_planejada_minutos=dur_rev,
                    questoes_planejadas=10,
                    status_tarefa="PENDENTE",
                    motivo_recomendacao=f"Revisão {rev.ciclo_revisao} programada para {rev.data_prevista.strftime('%d/%m/%Y')}.",
                )
            )
            ordem_seq += 1

        # =====================================================================
        # ETAPA 2 — PORTUGUÊS TODO DIA + 1 MATÉRIA DA FASE + DOSE TRANQUILA ANPD (DADOS & TI)
        # =====================================================================
        # 2A. BLOCO FIXO DIÁRIO: LÍNGUA PORTUGUESA (CEBRASPE + IAUPE)
        disc_port = disc_by_cod.get("PORT")
        if disc_port:
            tops_port = db.scalars(
                select(Topico)
                .where(Topico.disciplina_id == disc_port.id)
                .order_by(Topico.codigo_estavel.asc())
            ).all()
            if tops_port:
                top_port = tops_port[hoje.toordinal() % len(tops_port)]
                disciplinas_do_dia_ids.append(disc_port.id)
                db.add(
                    TarefaCronograma(
                        data_programada=hoje,
                        etapa_meu_dia=2,
                        nome_etapa="Português · todo dia",
                        ordem_no_dia=ordem_seq,
                        eixo_estrategico="EIXO_1_SEFAZ_PE",
                        disciplina_id=disc_port.id,
                        topico_id=top_port.id,
                        titulo_tarefa=f"Português: {top_port.titulo}",
                        duracao_planejada_minutos=45,
                        questoes_planejadas=15,
                        status_tarefa="PENDENTE",
                        motivo_recomendacao="Bloco fixo diário • Foco Cebraspe (reescrita, coesão, sintaxe) e IAUPE (SEFAZ-PE).",
                    )
                )
                ordem_seq += 1

        # 2B. MATÉRIA DO DIA = foco da semana do plano de 60 dias
        fase_atual = trilha["fase_codigo"]
        codigos_fase = trilha["codigos_materia"]
        if trilha["semana"]:
            etiqueta_fase = f"Semana {trilha['semana']} de 8 · {trilha['foco_semana']}"
        else:
            etiqueta_fase = trilha["foco_semana"]

        ids_fase = [disc_by_cod[c].id for c in codigos_fase if c in disc_by_cod]
        candidatos_fase = list(
            db.scalars(
                select(Topico).where(
                    Topico.disciplina_id.in_(ids_fase),
                    Topico.status_estudo != "DOMINADO",
                )
            ).all()
        )
        # Primeiro o que ainda não foi estudado; depois o que mais pesa
        candidatos_fase.sort(
            key=lambda t: (
                0 if t.status_estudo in ("NAO_INICIADO", "MATERIAL_LOCALIZADO") else 1,
                -t.score_importancia,
                t.codigo_estavel,
            )
        )

        if candidatos_fase:
            cod_disc_dia = codigos_fase[hoje.toordinal() % len(codigos_fase)]
            did_pref = disc_by_cod[cod_disc_dia].id if cod_disc_dia in disc_by_cod else None
            top_base = next(
                (t for t in candidatos_fase if t.disciplina_id == did_pref),
                candidatos_fase[0],
            )
            d_base = db.get(Disciplina, top_base.disciplina_id)
            if d_base:
                disciplinas_do_dia_ids.append(d_base.id)
            eixo_base = (
                "EIXO_2_ANPD_TI"
                if d_base and d_base.eixo_associado == "EIXO_2_ANPD_TI"
                else "EIXO_1_SEFAZ_PE"
            )
            db.add(
                TarefaCronograma(
                    data_programada=hoje,
                    etapa_meu_dia=2,
                    nome_etapa="Matéria do dia",
                    ordem_no_dia=ordem_seq,
                    eixo_estrategico=eixo_base,
                    disciplina_id=top_base.disciplina_id,
                    topico_id=top_base.id,
                    titulo_tarefa=f"{d_base.nome if d_base else 'Base'}: {top_base.titulo}",
                    duracao_planejada_minutos=60,
                    questoes_planejadas=15,
                    status_tarefa="PENDENTE",
                    motivo_recomendacao=etiqueta_fase,
                )
            )
            ordem_seq += 1

        # 2C. ANPD EM RITMO LEVE: três sessões semanais, sem competir com a base.
        if fase_atual != "FASE_3_ACELERACAO_ANPD" and trilha["anpd_hoje"]:
            codigos_ti = ["TI_CD_EST", "TI_ENG_DADOS", "TI_IA", "TI_GERAL"]
            ids_ti = [disc_by_cod[c].id for c in codigos_ti if c in disc_by_cod]
            tops_ti = db.scalars(
                select(Topico)
                .where(
                    Topico.disciplina_id.in_(ids_ti),
                    Topico.status_estudo != "DOMINADO",
                )
                .order_by(Topico.codigo_estavel.asc())
            ).all()
            if tops_ti:
                top_ti = tops_ti[hoje.toordinal() % len(tops_ti)]
                d_ti = db.get(Disciplina, top_ti.disciplina_id)
                db.add(
                    TarefaCronograma(
                        data_programada=hoje,
                        etapa_meu_dia=2,
                        nome_etapa="ANPD · Dados & TI · ritmo leve",
                        ordem_no_dia=ordem_seq,
                        eixo_estrategico="EIXO_2_ANPD_TI",
                        disciplina_id=top_ti.disciplina_id,
                        topico_id=top_ti.id,
                        titulo_tarefa=f"{d_ti.nome if d_ti else 'Dados & TI'}: {top_ti.titulo}",
                        duracao_planejada_minutos=30,
                        questoes_planejadas=5,
                        status_tarefa="PENDENTE",
                        motivo_recomendacao="Trilha ANPD em ritmo leve • Dados & TI para Cebraspe.",
                    )
                )
                ordem_seq += 1

        db.commit()
        tarefas_existentes = db.scalars(
            select(TarefaCronograma)
            .where(
                TarefaCronograma.data_programada == hoje,
                TarefaCronograma.status_tarefa != "TRANSFERIDA",
            )
            .order_by(TarefaCronograma.etapa_meu_dia, TarefaCronograma.ordem_no_dia)
        ).all()

    etapa_1 = [t for t in tarefas_existentes if t.etapa_meu_dia == 1]
    etapa_2 = [t for t in tarefas_existentes if t.etapa_meu_dia == 2]
    etapa_3 = [t for t in tarefas_existentes if t.etapa_meu_dia == 3]
    sessoes_hoje = db.scalars(
        select(SessaoEstudo)
        .where(SessaoEstudo.data_sessao == hoje)
        .order_by(SessaoEstudo.id.desc())
    ).all()

    juris_detalhes = {}
    for t3 in etapa_3:
        if t3.jurisprudencia_id:
            j_obj = db.get(EntendimentoJurisprudencia, t3.jurisprudencia_id)
            if j_obj:
                juris_detalhes[t3.id] = j_obj

    total_metas = len(tarefas_existentes)
    metas_concluidas = sum(
        1 for t in tarefas_existentes if t.status_tarefa == "CONCLUIDA"
    )
    progresso_dia_pct = (
        int(round(metas_concluidas / total_metas * 100)) if total_metas > 0 else 0
    )

    return {
        "data_referencia": hoje,
        "trilha_60d": trilha,
        "etapa_1_revisoes": etapa_1,
        "etapa_2_conteudos_novos": etapa_2,
        "etapa_3_jurisprudencia": etapa_3,
        "juris_detalhes": juris_detalhes,
        "etapa_4_sessoes_registradas": sessoes_hoje,
        "tem_revisao_pendente_bloqueante": any(
            t.status_tarefa != "CONCLUIDA" for t in etapa_1
        ),
        "total_metas_dia": total_metas,
        "metas_concluidas_dia": metas_concluidas,
        "progresso_dia_pct": progresso_dia_pct,
        "total_minutos_planejados": sum(
            t.duracao_planejada_minutos for t in tarefas_existentes
        ),
        "total_minutos_realizados": sum(s.duracao_minutos for s in sessoes_hoje),
    }


def registrar_aprendizado_etapa4(
    db: Session,
    disciplina_id: int,
    topico_id: Optional[int],
    duracao_minutos: int,
    tipo_sessao: str,
    questoes_realizadas: int,
    acertos: int,
    dificuldade_percebida: int,
    grau_compreensao: str,
    nivel_confianca: str,
    observacoes: str = "",
    tarefa_id: Optional[int] = None,
    agendar_revisao_d1: bool = True,
    data_sessao: Optional[date] = None,
) -> SessaoEstudo:
    """Registra o aprendizado na Etapa 4 do Meu Dia, atualiza o tópico e agenda a revisão D1."""
    ref = data_sessao or date.today()
    disc = db.get(Disciplina, disciplina_id)
    if not disc:
        raise ValueError("Disciplina inválida.")

    eixo = (
        "EIXO_2_ANPD_TI"
        if disc.eixo_associado == "EIXO_2_ANPD_TI"
        else "EIXO_1_SEFAZ_PE"
    )
    erros = max(0, questoes_realizadas - acertos)

    sessao = SessaoEstudo(
        data_sessao=ref,
        inicio_em=datetime.now() - timedelta(minutes=duracao_minutos),
        fim_em=datetime.now(),
        duracao_minutos=max(1, duracao_minutos),
        tipo_sessao=tipo_sessao,
        status_execucao="CONCLUIDA",
        eixo_estrategico=eixo,
        disciplina_id=disciplina_id,
        topico_id=topico_id,
        tarefa_cronograma_id=tarefa_id,
        questoes_realizadas=questoes_realizadas,
        acertos=acertos,
        erros=erros,
        dificuldade_percebida=dificuldade_percebida,
        grau_compreensao=grau_compreensao,
        nivel_confianca=nivel_confianca,
        observacoes=observacoes,
    )
    db.add(sessao)
    db.flush()

    if tarefa_id:
        tarefa = db.get(TarefaCronograma, tarefa_id)
        if tarefa:
            tarefa.status_tarefa = "CONCLUIDA"
            tarefa.duracao_realizada_minutos = duracao_minutos

    if topico_id:
        topico = db.get(Topico, topico_id)
        if topico:
            _atualizar_dominio_topico_baseado_em_evidencias(db, topico)
            # Agenda revisão inicial D1 se for estudo de conteúdo novo e ainda não houver revisão pendente
            if agendar_revisao_d1 and tipo_sessao in ("CONTEUDO_NOVO", "TEORIA", "LEGISLACAO"):
                rev_pendente = db.scalar(
                    select(Revisao).where(
                        Revisao.topico_id == topico_id,
                        Revisao.status_revisao.in_(["PENDENTE", "ATRASADA"]),
                    )
                )
                if not rev_pendente:
                    db.add(
                        Revisao(
                            topico_id=topico_id,
                            disciplina_id=disciplina_id,
                            sessao_origem_id=sessao.id,
                            ciclo_revisao="D1",
                            modalidade_revisao="Recuperação Ativa + Legislação + Questões",
                            intervalo_dias_aplicado=1,
                            data_prevista=ref + timedelta(days=1),
                            status_revisao="PENDENTE",
                        )
                    )

    db.commit()
    db.refresh(sessao)
    return sessao
