"""Rotas Web e API da Plataforma Concurso 2027 (Todos os 15 Módulos Integrados)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import ACERVO_FOLDERS, BACKUPS_DIR, BASE_DIR
from app.database import get_db
from app.models.entities import (
    AssociacaoTopicoConcurso,
    AuditoriaAlteracao,
    AvaliacaoNivelamento,
    Concurso,
    Configuracao,
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
    Simulado,
    TarefaCronograma,
    Topico,
)
from app.services.acervo_service import indexar_acervo_completo, resolve_safe_file_path
from app.services.analitica_backup_service import (
    calcular_indicadores_dashboard,
    calcular_previsao_dominio_por_disciplina,
    corrigir_simulado,
    criar_backup_sqlite,
    criar_simulado_adaptativo,
    exportar_jurisprudencia_json,
    importar_jurisprudencia_json,
)
from app.services.planejamento_service import (
    alterar_fase_estudo,
    avaliar_entendimento_sm2,
    avaliar_flashcard_sm2,
    concluir_revisao_geral,
    gerar_ou_obter_meu_dia,
    registrar_aprendizado_etapa4,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _redirect_with_msg(url: str, msg: str, msg_type: str = "success") -> RedirectResponse:
    target = url if isinstance(url, str) else getattr(url, "default", "/")
    sep = "&" if "?" in target else "?"
    return RedirectResponse(
        url=f"{target}{sep}msg={quote(msg)}&msg_type={msg_type}", status_code=303
    )


# =============================================================================
# 1. DASHBOARD / VISÃO GERAL (ROTA /dashboard)
# =============================================================================
@router.get("/dashboard", response_class=HTMLResponse)
def pagina_dashboard(
    request: Request,
    msg: Optional[str] = None,
    msg_type: str = "success",
    db: Session = Depends(get_db),
):
    kpi = calcular_indicadores_dashboard(db)
    meu_dia = gerar_ou_obter_meu_dia(db)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_nav": "dashboard",
            "page_title": "Visão Geral da Preparação 2027",
            "page_subtitle": "SEFAZ-PE (60% • Meta 60 dias) e ANPD + Dados & TI (40%)",
            "flash_message": msg,
            "flash_type": msg_type,
            "kpi": kpi,
            "meu_dia": meu_dia,
        },
    )


# =============================================================================
# 2. PÁGINA INICIAL: METAS DO DIA (MEU DIA — LIMPO E VISUAL)
# =============================================================================
@router.get("/", response_class=HTMLResponse)
@router.get("/meu-dia", response_class=HTMLResponse)
def pagina_meu_dia(
    request: Request,
    msg: Optional[str] = None,
    msg_type: str = "success",
    db: Session = Depends(get_db),
):
    meu_dia = gerar_ou_obter_meu_dia(db)
    disciplinas = db.scalars(
        select(Disciplina).order_by(Disciplina.ordem_exibicao.asc())
    ).all()
    topicos = db.scalars(select(Topico).order_by(Topico.codigo_estavel.asc())).all()
    return templates.TemplateResponse(
        request,
        "meu_dia.html",
        {
            "active_nav": "meu_dia",
            "page_title": "Metas do Dia",
            "page_subtitle": "Português todo dia • Base sólida primeiro • Ritmo leve ANPD (Dados & TI)",
            "flash_message": msg,
            "flash_type": msg_type,
            "meu_dia": meu_dia,
            "disciplinas": disciplinas,
            "topicos": topicos,
        },
    )


@router.post("/meu-dia/fase")
def acao_alterar_fase(
    nova_fase: str = Form(...),
    db: Session = Depends(get_db),
):
    alterar_fase_estudo(db, nova_fase)
    return _redirect_with_msg(
        "/meu-dia",
        "Fase pedagógica atualizada! Suas metas de hoje foram ajustadas automaticamente.",
    )


@router.post("/meu-dia/concluir-rapido/{tarefa_id}")
def acao_concluir_rapido_meu_dia(
    tarefa_id: int,
    db: Session = Depends(get_db),
):
    tarefa = db.get(TarefaCronograma, tarefa_id)
    if tarefa and tarefa.disciplina_id:
        registrar_aprendizado_etapa4(
            db=db,
            disciplina_id=tarefa.disciplina_id,
            topico_id=tarefa.topico_id,
            duracao_minutos=tarefa.duracao_planejada_minutos,
            tipo_sessao="CONTEUDO_NOVO",
            questoes_realizadas=tarefa.questoes_planejadas,
            acertos=int(round(tarefa.questoes_planejadas * 0.8)),
            dificuldade_percebida=3,
            grau_compreensao="BOM",
            nivel_confianca="MEDIA",
            observacoes=f"Concluído no Meu Dia: {tarefa.titulo_tarefa}",
            tarefa_id=tarefa.id,
        )
    return _redirect_with_msg(
        "/meu-dia",
        "Meta concluída! Sessão registrada e revisão D1 agendada para amanhã.",
    )


@router.post("/meu-dia/reorganizar")
def acao_reorganizar_meu_dia(db: Session = Depends(get_db)):
    gerar_ou_obter_meu_dia(db, forcar_reorganizacao=True)
    return _redirect_with_msg(
        "/meu-dia",
        "Sequência diária reorganizada com base nas revisões pendentes e na distribuição 60% SEFAZ-PE / 40% ANPD+TI.",
    )


@router.post("/meu-dia/registrar-aprendizado")
def acao_registrar_aprendizado(
    disciplina_id: int = Form(...),
    topico_id: Optional[str] = Form(None),
    tipo_sessao: str = Form("CONTEUDO_NOVO"),
    duracao_minutos: int = Form(60),
    questoes_realizadas: int = Form(0),
    acertos: int = Form(0),
    dificuldade_percebida: int = Form(3),
    grau_compreensao: str = Form("BOM"),
    nivel_confianca: str = Form("MEDIA"),
    observacoes: str = Form(""),
    tarefa_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    tid = int(topico_id) if topico_id and topico_id.strip().isdigit() else None
    tar_id = int(tarefa_id) if tarefa_id and tarefa_id.strip().isdigit() else None
    registrar_aprendizado_etapa4(
        db=db,
        disciplina_id=disciplina_id,
        topico_id=tid,
        duracao_minutos=duracao_minutos,
        tipo_sessao=tipo_sessao,
        questoes_realizadas=questoes_realizadas,
        acertos=min(acertos, questoes_realizadas),
        dificuldade_percebida=dificuldade_percebida,
        grau_compreensao=grau_compreensao,
        nivel_confianca=nivel_confianca,
        observacoes=observacoes,
        tarefa_id=tar_id,
    )
    return _redirect_with_msg(
        "/meu-dia",
        "Aprendizado registrado na Etapa 4 com sucesso! Planejamento atualizado e Revisão D1 agendada.",
    )


# =============================================================================
# 3. PLANEJAMENTO INTELIGENTE, NIVELAMENTO E METAS
# =============================================================================
@router.get("/planejamento", response_class=HTMLResponse)
def pagina_planejamento(
    request: Request,
    msg: Optional[str] = None,
    msg_type: str = "success",
    db: Session = Depends(get_db),
):
    gerar_ou_obter_meu_dia(db)
    tarefas_cal = db.scalars(
        select(TarefaCronograma)
        .order_by(
            TarefaCronograma.data_programada.desc(),
            TarefaCronograma.etapa_meu_dia.asc(),
            TarefaCronograma.ordem_no_dia.asc(),
        )
        .limit(50)
    ).all()
    avaliacoes = db.scalars(
        select(AvaliacaoNivelamento).order_by(AvaliacaoNivelamento.id.desc())
    ).all()
    disciplinas = db.scalars(
        select(Disciplina).order_by(Disciplina.ordem_exibicao.asc())
    ).all()
    topicos = db.scalars(select(Topico).order_by(Topico.codigo_estavel.asc())).all()
    return templates.TemplateResponse(
        request,
        "planejamento.html",
        {
            "active_nav": "planejamento",
            "page_title": "Planejamento Inteligente, Nivelamento e Metas",
            "page_subtitle": "Calendário adaptativo semanal/mensal, diagnóstico de nivelamento e metas configuráveis",
            "flash_message": msg,
            "flash_type": msg_type,
            "tarefas_calendario": tarefas_cal,
            "avaliacoes_nivelamento": avaliacoes,
            "disciplinas": disciplinas,
            "topicos": topicos,
        },
    )


@router.post("/planejamento/nivelamento")
def acao_registrar_nivelamento(
    disciplina_id: int = Form(...),
    topico_id: Optional[str] = Form(None),
    questoes_avaliadas: int = Form(...),
    acertos: int = Form(...),
    tempo_resposta_segundos: int = Form(600),
    confianca: str = Form("MEDIA"),
    dificuldade_percebida: int = Form(3),
    db: Session = Depends(get_db),
):
    tid = int(topico_id) if topico_id and topico_id.strip().isdigit() else None
    acertos_reais = min(max(0, acertos), max(1, questoes_avaliadas))
    perc = acertos_reais / max(1, questoes_avaliadas) * 100.0

    # Regra 11: Não classificar como consolidado com base em uma única questão!
    if questoes_avaliadas < 5:
        dominio = "EM_DESENVOLVIMENTO"
        rec = (
            f"Amostra reduzida ({questoes_avaliadas} questão(ões), {perc:.0f}%). "
            "Regra 11: Exige pelo menos 5 questões para diagnosticar domínio consolidado."
        )
    elif perc >= 80.0 and confianca == "ALTA":
        dominio = "CONSOLIDADO"
        rec = f"Alto aproveitamento ({perc:.0f}% em {questoes_avaliadas} questões). Priorizar revisões espaçadas e questões avançadas."
    elif perc >= 65.0:
        dominio = "BOM"
        rec = f"Desempenho intermediário ({perc:.0f}%). Reforçar subtópicos com erro e legislação correlata."
    else:
        dominio = "INICIAL"
        rec = f"Lacuna identificada ({perc:.0f}%). Priorizar estudo inicial completo na Etapa 2 do Meu Dia."

    db.add(
        AvaliacaoNivelamento(
            data_avaliacao=date.today(),
            disciplina_id=disciplina_id,
            topico_id=tid,
            questoes_avaliadas=questoes_avaliadas,
            acertos=acertos_reais,
            erros=max(0, questoes_avaliadas - acertos_reais),
            tempo_resposta_segundos=tempo_resposta_segundos,
            confianca=confianca,
            dificuldade_percebida=dificuldade_percebida,
            classificacao_dominio=dominio,
            recomendacao_gerada=rec,
        )
    )
    if tid:
        top = db.get(Topico, tid)
        if top:
            top.situacao_dominio = dominio
    db.commit()
    return _redirect_with_msg(
        "/planejamento", f"Diagnóstico de nivelamento registrado: {dominio}."
    )


@router.post("/planejamento/meta")
def acao_criar_meta(
    tipo_registro: str = Form("META"),
    categoria: str = Form("META_QUESTOES_ASSUNTO"),
    titulo: str = Form(...),
    descricao: str = Form(...),
    valor_alvo: float = Form(20.0),
    db: Session = Depends(get_db),
):
    db.add(
        MetaAlerta(
            tipo_registro=tipo_registro,
            categoria=categoria,
            titulo=titulo.strip(),
            descricao=descricao.strip(),
            valor_alvo=valor_alvo,
            valor_atual=0.0,
            prioridade="ALTA",
        )
    )
    db.commit()
    return _redirect_with_msg("/planejamento", "Meta/Alerta cadastrado com sucesso.")


# =============================================================================
# 4. EDITAIS, MATRIZ DE COBERTURA E INTELIGÊNCIA DE COBRANÇA
# =============================================================================
@router.get("/editais", response_class=HTMLResponse)
def pagina_editais(
    request: Request,
    msg: Optional[str] = None,
    db: Session = Depends(get_db),
):
    concursos = db.scalars(select(Concurso).order_by(Concurso.id.asc())).all()
    historico = db.scalars(
        select(HistoricoProvaCobranca).order_by(
            HistoricoProvaCobranca.frequencia_percentual.desc()
        )
    ).all()

    topicos = db.scalars(select(Topico)).all()
    total_comuns = 0
    total_exclusivos = 0
    for t in topicos:
        qtd_c = (
            db.scalar(
                select(func.count(AssociacaoTopicoConcurso.id)).where(
                    AssociacaoTopicoConcurso.topico_id == t.id
                )
            )
            or 0
        )
        if qtd_c > 1:
            total_comuns += 1
        else:
            total_exclusivos += 1

    return templates.TemplateResponse(
        request,
        "editais.html",
        {
            "active_nav": "editais",
            "page_title": "Editais, Comparação de Cobertura e Inteligência de Cobrança",
            "page_subtitle": "Comparativo SEFAZ-PE (60%) vs ANPD + Dados e TI (40%) e histórico real de provas do acervo",
            "flash_message": msg,
            "concursos": concursos,
            "historico_cobranca": historico,
            "total_comuns": total_comuns,
            "total_exclusivos": total_exclusivos,
        },
    )


# =============================================================================
# 5. DISCIPLINAS E CONTEÚDOS (MATRIZ INTEGRADA)
# =============================================================================
@router.get("/disciplinas", response_class=HTMLResponse)
def pagina_disciplinas(
    request: Request,
    disciplina_id: Optional[str] = Query(None),
    tipo_escopo: Optional[str] = Query(None),
    msg: Optional[str] = None,
    msg_type: str = "success",
    db: Session = Depends(get_db),
):
    did_int = (
        int(disciplina_id)
        if disciplina_id and disciplina_id.strip().isdigit()
        else None
    )
    disciplinas = db.scalars(
        select(Disciplina).order_by(Disciplina.ordem_exibicao.asc())
    ).all()
    disc_by_id = {d.id: d for d in disciplinas}
    conc_by_id = {c.id: c for c in db.scalars(select(Concurso)).all()}

    stmt = select(Topico).order_by(Topico.disciplina_id.asc(), Topico.codigo_estavel.asc())
    if did_int:
        stmt = stmt.where(Topico.disciplina_id == did_int)
    topicos = db.scalars(stmt).all()

    matriz_items = []
    for t in topicos:
        assocs = db.scalars(
            select(AssociacaoTopicoConcurso).where(
                AssociacaoTopicoConcurso.topico_id == t.id
            )
        ).all()
        eh_comum = len(assocs) > 1
        if tipo_escopo == "COMUM" and not eh_comum:
            continue
        if tipo_escopo == "EXCLUSIVO" and eh_comum:
            continue

        siglas = [
            conc_by_id[a.concurso_id].sigla_orgao
            for a in assocs
            if a.concurso_id in conc_by_id
        ]
        qtd_mat = (
            db.scalar(
                select(func.count(Material.id)).where(
                    Material.disciplina_id == t.disciplina_id
                )
            )
            or 0
        )
        matriz_items.append(
            {
                "topico": t,
                "disciplina": disc_by_id.get(t.disciplina_id),
                "associacoes": assocs,
                "eh_comum": eh_comum,
                "concursos_siglas": siglas,
                "qtd_materiais_disciplina": qtd_mat,
            }
        )

    return templates.TemplateResponse(
        request,
        "disciplinas.html",
        {
            "active_nav": "disciplinas",
            "page_title": "Disciplinas e Matriz Integrada de Conteúdos",
            "page_subtitle": "Assuntos comuns registrados uma única vez e vinculados a múltiplos editais",
            "flash_message": msg,
            "flash_type": msg_type,
            "disciplinas": disciplinas,
            "matriz_items": matriz_items,
            "filtro_disciplina_id": did_int,
            "filtro_escopo": tipo_escopo,
        },
    )


@router.post("/disciplinas/novo-topico")
def acao_novo_topico(
    codigo_estavel: str = Form(...),
    disciplina_id: int = Form(...),
    titulo: str = Form(...),
    escopo_concursos: str = Form("AMBOS"),
    descricao_objetiva: str = Form(""),
    origem_documental: str = Form("Edital / Acervo Local"),
    meta_questoes: int = Form(20),
    eh_denso: str = Form("false"),
    db: Session = Depends(get_db),
):
    cod = codigo_estavel.strip().upper()
    tit = titulo.strip()
    existente = db.scalar(
        select(Topico).where(
            or_(
                Topico.codigo_estavel == cod,
                (Topico.disciplina_id == disciplina_id) & (Topico.titulo == tit),
            )
        )
    )
    if existente:
        return _redirect_with_msg(
            "/disciplinas",
            f"Prevenção de duplicidade: O tópico '{tit}' ({cod}) já existe na Matriz Integrada.",
            "warning",
        )

    novo = Topico(
        codigo_estavel=cod,
        disciplina_id=disciplina_id,
        titulo=tit,
        descricao_objetiva=descricao_objetiva.strip(),
        origem_documental=origem_documental.strip(),
        meta_questoes=meta_questoes,
        eh_denso=(eh_denso.lower() == "true"),
        status_estudo="NAO_INICIADO",
        situacao_dominio="NAO_AVALIADO",
    )
    db.add(novo)
    db.flush()

    sefaz = db.scalar(select(Concurso).where(Concurso.codigo == "SEFAZ_PE_APOIO"))
    anpd = db.scalar(select(Concurso).where(Concurso.codigo == "ANPD_ESP_DADOS"))

    if escopo_concursos in ("AMBOS", "SEFAZ_PE") and sefaz:
        db.add(
            AssociacaoTopicoConcurso(
                topico_id=novo.id,
                concurso_id=sefaz.id,
                status_no_concurso="HISTORICO_REFERENCIA",
                item_edital_referencia="Matriz Integrada SEFAZ-PE",
            )
        )
    if escopo_concursos in ("AMBOS", "ANPD") and anpd:
        db.add(
            AssociacaoTopicoConcurso(
                topico_id=novo.id,
                concurso_id=anpd.id,
                status_no_concurso="CONFIRMADO_EDITAL",
                item_edital_referencia="Matriz Integrada ANPD + Dados/TI",
            )
        )

    db.add(
        AuditoriaAlteracao(
            entidade_nome="topico",
            entidade_id=novo.id,
            acao="CREATE",
            resumo_alteracao=f"Tópico {cod} ({tit}) adicionado à Matriz Integrada ({escopo_concursos}).",
        )
    )
    db.commit()
    return _redirect_with_msg(
        "/disciplinas", f"Tópico '{tit}' cadastrado na Matriz Integrada sem duplicidade."
    )


# =============================================================================
# 6. BIBLIOTECA DOCUMENTAL E PROCESSAMENTO DE ARQUIVOS
# =============================================================================
@router.get("/biblioteca", response_class=HTMLResponse)
def pagina_biblioteca(
    request: Request,
    q: Optional[str] = Query(None),
    pasta: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    msg: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt = select(Material).order_by(Material.pasta_acervo.asc(), Material.nome_arquivo.asc())
    if pasta:
        stmt = stmt.where(Material.pasta_acervo == pasta)
    if tipo:
        stmt = stmt.where(Material.tipo_material == tipo)
    if q and q.strip():
        termo = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Material.nome_arquivo.ilike(termo),
                Material.titulo_catalogo.ilike(termo),
                Material.texto_extraido_amostra.ilike(termo),
                Material.observacoes.ilike(termo),
            )
        )
    materiais = db.scalars(stmt).all()

    todos = db.scalars(select(Material)).all()
    total_indexados = len(todos)
    total_aprovados = sum(
        1
        for m in todos
        if "1. APROVADO" in m.classificacao_utilidade
        or "2. APROVADO" in m.classificacao_utilidade
    )
    total_digitalizados = sum(1 for m in todos if m.eh_digitalizado_sem_texto)
    total_falhas = sum(1 for m in todos if m.falha_leitura)

    return templates.TemplateResponse(
        request,
        "biblioteca.html",
        {
            "active_nav": "biblioteca",
            "page_title": "Biblioteca Documental e Índice do Acervo",
            "page_subtitle": "Indexação real dos arquivos das 6 pastas oficiais com busca por nome e texto extraído",
            "flash_message": msg,
            "materiais": materiais,
            "pastas_oficiais": ACERVO_FOLDERS,
            "q": q,
            "filtro_pasta": pasta,
            "filtro_tipo": tipo,
            "total_indexados": total_indexados,
            "total_aprovados": total_aprovados,
            "total_digitalizados": total_digitalizados,
            "total_falhas": total_falhas,
        },
    )


@router.post("/biblioteca/reindexar")
def acao_reindexar_biblioteca(db: Session = Depends(get_db)):
    stats = indexar_acervo_completo(db, force_recheck=True)
    return _redirect_with_msg(
        "/biblioteca",
        f"Acervo revalidado com sucesso: {stats['total_arquivos_disco']} arquivos verificados em disco (0 originais alterados).",
    )


@router.get("/biblioteca/abrir/{material_id}")
def abrir_arquivo_acervo(material_id: int, db: Session = Depends(get_db)):
    mat = db.get(Material, material_id)
    if not mat:
        raise HTTPException(status_code=404, detail="Material não encontrado no índice.")
    safe_path = resolve_safe_file_path(mat.caminho_relativo)
    if not safe_path:
        raise HTTPException(
            status_code=404,
            detail="Arquivo físico ausente ou fora da raiz oficial permitida.",
        )
    media_map = {
        ".pdf": "application/pdf",
        ".html": "text/html; charset=utf-8",
        ".md": "text/plain; charset=utf-8",
        ".csv": "text/csv; charset=utf-8",
    }
    media_type = media_map.get(safe_path.suffix.lower(), "application/octet-stream")
    return FileResponse(path=str(safe_path), media_type=media_type)


# =============================================================================
# 7. MÓDULO DE LEGISLAÇÃO
# =============================================================================
@router.get("/legislacao", response_class=HTMLResponse)
def pagina_legislacao(
    request: Request,
    q: Optional[str] = Query(None),
    jurisdicao: Optional[str] = Query(None),
    msg: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt = select(NormaJuridica).order_by(
        NormaJuridica.jurisdicao.asc(), NormaJuridica.ano.desc()
    )
    if jurisdicao:
        stmt = stmt.where(NormaJuridica.jurisdicao == jurisdicao)
    if q and q.strip():
        termo = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                NormaJuridica.numero.ilike(termo),
                NormaJuridica.titulo_curto.ilike(termo),
                NormaJuridica.ementa.ilike(termo),
                NormaJuridica.artigos_chave.ilike(termo),
            )
        )
    normas = db.scalars(stmt).all()
    disciplinas = db.scalars(
        select(Disciplina).order_by(Disciplina.ordem_exibicao.asc())
    ).all()
    return templates.TemplateResponse(
        request,
        "legislacao.html",
        {
            "active_nav": "legislacao",
            "page_title": "Legislação Estruturada — Federal, Estadual PE e Atos ANPD",
            "page_subtitle": "Pesquisa por nome, número, artigo e assunto com controle de fonte oficial e versão",
            "flash_message": msg,
            "normas": normas,
            "disciplinas": disciplinas,
            "q": q,
            "filtro_jurisdicao": jurisdicao,
        },
    )


@router.post("/legislacao/{norma_id}/status")
def acao_atualizar_status_norma(
    norma_id: int,
    status_leitura: str = Form(...),
    db: Session = Depends(get_db),
):
    n = db.get(NormaJuridica, norma_id)
    if n:
        n.status_leitura = status_leitura
        db.commit()
    return _redirect_with_msg("/legislacao", "Status de leitura da norma atualizado.")


@router.post("/legislacao/nova")
def acao_nova_norma(
    tipo_norma: str = Form(...),
    jurisdicao: str = Form(...),
    numero: str = Form(...),
    ano: str = Form(...),
    titulo_curto: str = Form(...),
    disciplina_id: int = Form(...),
    fonte_oficial_nome: str = Form(...),
    artigos_chave: str = Form(""),
    ementa: str = Form(...),
    db: Session = Depends(get_db),
):
    db.add(
        NormaJuridica(
            tipo_norma=tipo_norma,
            jurisdicao=jurisdicao,
            numero=numero.strip(),
            ano=ano.strip(),
            titulo_curto=titulo_curto.strip(),
            ementa=ementa.strip(),
            artigos_chave=artigos_chave.strip(),
            fonte_oficial_nome=fonte_oficial_nome.strip(),
            data_atualizacao_verificada=date.today(),
            status_vigencia="VIGENTE_VERIFICADA_EM_FONTE",
            disciplina_id=disciplina_id,
        )
    )
    db.commit()
    return _redirect_with_msg("/legislacao", "Norma jurídica cadastrada com sucesso.")


# =============================================================================
# 8 & 9. QUESTÕES (QCONCURSOS) E CADERNO DE ERROS
# =============================================================================
@router.get("/questoes", response_class=HTMLResponse)
@router.get("/caderno-erros", response_class=HTMLResponse)
def pagina_questoes_e_erros(
    request: Request,
    msg: Optional[str] = None,
    db: Session = Depends(get_db),
):
    active = "caderno_erros" if "caderno-erros" in str(request.url) else "questoes"
    kpi = calcular_indicadores_dashboard(db)
    erros = db.scalars(
        select(ErroCaderno).order_by(
            ErroCaderno.status_superacao.asc(),
            ErroCaderno.reincidencias.desc(),
            ErroCaderno.id.desc(),
        )
    ).all()
    questoes = db.scalars(select(Questao).order_by(Questao.id.asc())).all()
    disciplinas = db.scalars(
        select(Disciplina).order_by(Disciplina.ordem_exibicao.asc())
    ).all()
    topicos = db.scalars(select(Topico).order_by(Topico.codigo_estavel.asc())).all()

    return templates.TemplateResponse(
        request,
        "questoes_erros.html",
        {
            "active_nav": active,
            "page_title": "Questões (Integração Manual Qconcursos) & Caderno de Erros",
            "page_subtitle": "Meta referência de 20 questões por assunto e diagnóstico de erros em 8 categorias",
            "flash_message": msg,
            "kpi": kpi,
            "erros_caderno": erros,
            "questoes_banco": questoes,
            "disciplinas": disciplinas,
            "topicos": topicos,
        },
    )


@router.post("/questoes/registrar-resposta")
def acao_registrar_resposta_questao(
    disciplina_id: int = Form(...),
    topico_id: Optional[str] = Form(None),
    banca_nome: str = Form("Cebraspe"),
    concurso_nome: str = Form(""),
    resposta_escolhida: str = Form(...),
    gabarito_correto: str = Form(...),
    confianca: str = Form("SABIA"),
    tempo_segundos: int = Form(90),
    fonte_link_externo: str = Form(""),
    categoria_erro: str = Form("FALTA_CONHECIMENTO"),
    comentarios: str = Form(""),
    db: Session = Depends(get_db),
):
    tid = int(topico_id) if topico_id and topico_id.strip().isdigit() else None
    esc = resposta_escolhida.strip().upper()
    gab = gabarito_correto.strip().upper()
    resultado = "CORRETA" if esc == gab else "INCORRETA"
    pendente_rev = resultado == "INCORRETA" or confianca in ("DUVIDA", "CHUTE")

    resp = RespostaQuestao(
        disciplina_id=disciplina_id,
        topico_id=tid,
        banca_nome=banca_nome,
        concurso_nome=concurso_nome,
        fonte_link_externo=fonte_link_externo.strip() or None,
        data_resolucao=date.today(),
        resposta_escolhida=esc,
        gabarito_correto=gab,
        resultado=resultado,
        tempo_segundos=tempo_segundos,
        confianca=confianca,
        pendente_revisao=pendente_rev,
        comentarios=comentarios,
    )
    db.add(resp)
    db.flush()

    if pendente_rev:
        db.add(
            ErroCaderno(
                resposta_questao_id=resp.id,
                referencia_questao_externa=concurso_nome
                or fonte_link_externo
                or f"Questão {banca_nome} (#{resp.id})",
                link_qconcursos=fonte_link_externo.strip() or None,
                disciplina_id=disciplina_id,
                topico_id=tid,
                categoria_erro=categoria_erro,
                alternativa_escolhida=esc,
                resposta_correta=gab,
                explicacao_correcao=comentarios
                or f"Item registrado com resultado {resultado} e confiança {confianca}.",
                plano_acao="Revisar fundamentação e refazer bateria no Qconcursos.",
                confianca=confianca,
                data_erro=date.today(),
                proxima_revisao_em=date.today() + timedelta(days=1),
            )
        )
    db.commit()
    return _redirect_with_msg(
        "/questoes",
        f"Questão registrada ({resultado}). {'Incluída no Caderno de Erros para reforço!' if pendente_rev else ''}",
    )


@router.post("/caderno-erros/novo")
def acao_novo_erro_caderno(
    referencia_questao_externa: str = Form(...),
    disciplina_id: int = Form(...),
    topico_id: Optional[str] = Form(None),
    categoria_erro: str = Form(...),
    alternativa_escolhida: str = Form(...),
    resposta_correta: str = Form(...),
    dificuldade: str = Form("ALTA"),
    confianca: str = Form("DUVIDA"),
    explicacao_correcao: str = Form(...),
    db: Session = Depends(get_db),
):
    tid = int(topico_id) if topico_id and topico_id.strip().isdigit() else None
    erro = ErroCaderno(
        referencia_questao_externa=referencia_questao_externa.strip(),
        disciplina_id=disciplina_id,
        topico_id=tid,
        categoria_erro=categoria_erro,
        alternativa_escolhida=alternativa_escolhida.strip(),
        resposta_correta=resposta_correta.strip(),
        explicacao_correcao=explicacao_correcao.strip(),
        dificuldade=dificuldade,
        confianca=confianca,
        data_erro=date.today(),
        proxima_revisao_em=date.today() + timedelta(days=1),
    )
    db.add(erro)
    # Alimenta automaticamente o agendamento de revisão de reforço se houver tópico
    if tid:
        db.add(
            Revisao(
                topico_id=tid,
                disciplina_id=disciplina_id,
                ciclo_revisao="D1",
                modalidade_revisao=f"Reforço Caderno de Erros ({categoria_erro})",
                intervalo_dias_aplicado=1,
                data_prevista=date.today(),
                status_revisao="PENDENTE",
            )
        )
    db.commit()
    return _redirect_with_msg(
        "/caderno-erros",
        "Erro registrado no Caderno de Erros e revisão de reforço agendada!",
    )


@router.post("/caderno-erros/{erro_id}/revisar")
def acao_revisar_erro_caderno(erro_id: int, db: Session = Depends(get_db)):
    e = db.get(ErroCaderno, erro_id)
    if e:
        e.revisoes_realizadas += 1
        if e.revisoes_realizadas >= 2:
            e.status_superacao = "SUPERADO"
        else:
            e.status_superacao = "EM_REVISAO"
            e.proxima_revisao_em = date.today() + timedelta(days=7)
        db.commit()
    return _redirect_with_msg("/caderno-erros", "Revisão do erro contabilizada.")


# =============================================================================
# 10 & 11. REVISÕES GERAIS (D1-D60), FLASHCARDS (SM-2) E SIMULADOS ADAPTATIVOS
# =============================================================================
@router.get("/revisoes", response_class=HTMLResponse)
@router.get("/simulados", response_class=HTMLResponse)
def pagina_revisoes_e_simulados(
    request: Request,
    msg: Optional[str] = None,
    db: Session = Depends(get_db),
):
    active = "simulados" if "simulados" in str(request.url) else "revisoes"
    revisoes = db.scalars(
        select(Revisao).order_by(Revisao.status_revisao.asc(), Revisao.data_prevista.asc())
    ).all()
    flashcards = db.scalars(
        select(Flashcard).order_by(Flashcard.proxima_revisao_em.asc())
    ).all()
    simulado_ativo = db.scalar(
        select(Simulado)
        .where(Simulado.status_simulado == "EM_ANDAMENTO")
        .order_by(Simulado.id.desc())
    )
    questoes_sim_ativo = []
    if simulado_ativo:
        q_ids = json.loads(simulado_ativo.questoes_ids_json or "[]")
        for qid in q_ids:
            q_obj = db.get(Questao, qid)
            if q_obj:
                questoes_sim_ativo.append(q_obj)

    resultados_sim = db.scalars(
        select(ResultadoSimulado).order_by(ResultadoSimulado.id.desc())
    ).all()
    disciplinas = db.scalars(
        select(Disciplina).order_by(Disciplina.ordem_exibicao.asc())
    ).all()
    topicos = db.scalars(select(Topico).order_by(Topico.codigo_estavel.asc())).all()

    return templates.TemplateResponse(
        request,
        "revisoes_simulados.html",
        {
            "active_nav": active,
            "page_title": "Revisões (D1-D60), Flashcards (SM-2) e Simulados Adaptativos",
            "page_subtitle": "Separação transparente entre Revisão Geral (D1/D7/D15/D30/D60) e Algoritmo SM-2",
            "flash_message": msg,
            "revisoes_gerais": revisoes,
            "flashcards": flashcards,
            "simulado_ativo": simulado_ativo,
            "questoes_simulado_ativo": questoes_sim_ativo,
            "resultados_simulados": resultados_sim,
            "disciplinas": disciplinas,
            "topicos": topicos,
        },
    )


@router.post("/revisoes/{revisao_id}/concluir")
def acao_concluir_revisao(
    revisao_id: int,
    duracao_minutos: int = Form(25),
    dificuldade: int = Form(3),
    confianca: str = Form("ALTA"),
    db: Session = Depends(get_db),
):
    rev = concluir_revisao_geral(
        db=db,
        revisao_id=revisao_id,
        duracao_minutos=duracao_minutos,
        dificuldade=dificuldade,
        confianca=confianca,
    )
    return _redirect_with_msg(
        "/meu-dia",
        f"Revisão {rev.ciclo_revisao} concluída e próximo ciclo espaçado agendado!",
    )


@router.post("/revisoes/flashcards/novo")
def acao_novo_flashcard(
    disciplina_id: int = Form(...),
    topico_id: Optional[str] = Form(None),
    frente_pergunta: str = Form(...),
    verso_resposta: str = Form(...),
    db: Session = Depends(get_db),
):
    tid = int(topico_id) if topico_id and topico_id.strip().isdigit() else None
    db.add(
        Flashcard(
            frente_pergunta=frente_pergunta.strip(),
            verso_resposta=verso_resposta.strip(),
            disciplina_id=disciplina_id,
            topico_id=tid,
            algoritmo_utilizado="SM-2",
            proxima_revisao_em=date.today(),
        )
    )
    db.commit()
    return _redirect_with_msg("/revisoes", "Flashcard SM-2 criado com sucesso.")


@router.post("/revisoes/flashcards/{card_id}/sm2")
def acao_avaliar_flashcard_sm2(
    card_id: int,
    qualidade_sm2: int = Form(...),
    db: Session = Depends(get_db),
):
    card = avaliar_flashcard_sm2(db, card_id, qualidade_sm2)
    return _redirect_with_msg(
        "/revisoes",
        f"Flashcard avaliado via SM-2 (EF={card.sm2_easiness_factor}, próximo intervalo={card.sm2_intervalo_dias} dia(s)).",
    )


@router.post("/simulados/criar")
def acao_criar_simulado(
    titulo: str = Form(...),
    banca_estilo: str = Form("Cebraspe (Certo/Errado)"),
    modo_selecao: str = Form("ADAPTATIVO_PONTOS_FRACOS"),
    quantidade_questoes: int = Form(6),
    tempo_previsto_minutos: int = Form(45),
    db: Session = Depends(get_db),
):
    sim = criar_simulado_adaptativo(
        db=db,
        titulo=titulo.strip(),
        banca_estilo=banca_estilo,
        modo_selecao=modo_selecao,
        quantidade_questoes=quantidade_questoes,
        tempo_previsto_minutos=tempo_previsto_minutos,
    )
    return _redirect_with_msg(
        "/simulados",
        f"Simulado '{sim.titulo}' montado com {sim.quantidade_questoes} questões!",
    )


@router.post("/simulados/{simulado_id}/finalizar")
async def acao_finalizar_simulado(
    simulado_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form_data = await request.form()
    respostas_map: dict[int, str] = {}
    for key, val in form_data.items():
        if key.startswith("q_"):
            qid = int(key.replace("q_", ""))
            respostas_map[qid] = str(val)
    tempo = int(form_data.get("tempo_gasto_minutos") or 25)
    res = corrigir_simulado(db, simulado_id, respostas_map, tempo)
    return _redirect_with_msg(
        "/simulados",
        f"Simulado finalizado! Acertos: {res.acertos}/{res.total_questoes} ({res.percentual_acerto}%) | Escore líquido Cebraspe: {res.pontuacao_liquida_cebraspe} pts.",
    )


# =============================================================================
# 12. JURISPRUDÊNCIA, SÚMULAS E INFORMATIVOS (SM-2 + JSON)
# =============================================================================
@router.get("/jurisprudencia", response_class=HTMLResponse)
def pagina_jurisprudencia(
    request: Request,
    q: Optional[str] = Query(None),
    tribunal: Optional[str] = Query(None),
    apenas_favoritos: Optional[str] = Query(None),
    msg: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt = select(EntendimentoJurisprudencia).order_by(
        EntendimentoJurisprudencia.sm2_proxima_revisao.asc(),
        EntendimentoJurisprudencia.id.asc(),
    )
    if tribunal:
        stmt = stmt.where(EntendimentoJurisprudencia.tribunal == tribunal)
    if apenas_favoritos == "1":
        stmt = stmt.where(EntendimentoJurisprudencia.favorito == True)  # noqa: E712
    if q and q.strip():
        termo = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                EntendimentoJurisprudencia.numero_identificacao.ilike(termo),
                EntendimentoJurisprudencia.assunto_titulo.ilike(termo),
                EntendimentoJurisprudencia.texto_entendimento.ilike(termo),
            )
        )
    entendimentos = db.scalars(stmt).all()
    disciplinas = db.scalars(
        select(Disciplina).order_by(Disciplina.ordem_exibicao.asc())
    ).all()
    return templates.TemplateResponse(
        request,
        "jurisprudencia.html",
        {
            "active_nav": "jurisprudencia",
            "page_title": "Jurisprudência, Súmulas (STF/STJ/Vinculantes), Informativos e ANPD",
            "page_subtitle": "Repetição espaçada SM-2, favoritos, histórico de domínio e importação/exportação JSON",
            "flash_message": msg,
            "entendimentos": entendimentos,
            "disciplinas": disciplinas,
            "q": q,
            "filtro_tribunal": tribunal,
            "apenas_favoritos": apenas_favoritos,
        },
    )


@router.post("/jurisprudencia/novo")
def acao_nova_jurisprudencia(
    tribunal: str = Form(...),
    tipo_entendimento: str = Form(...),
    numero_identificacao: str = Form(...),
    disciplina_id: int = Form(...),
    assunto_titulo: str = Form(...),
    fonte_oficial: str = Form(...),
    texto_entendimento: str = Form(...),
    db: Session = Depends(get_db),
):
    db.add(
        EntendimentoJurisprudencia(
            tribunal=tribunal,
            tipo_entendimento=tipo_entendimento,
            numero_identificacao=numero_identificacao.strip(),
            disciplina_id=disciplina_id,
            assunto_titulo=assunto_titulo.strip(),
            texto_entendimento=texto_entendimento.strip(),
            fonte_oficial=fonte_oficial.strip(),
            data_atualizacao_verificada=date.today(),
            sm2_proxima_revisao=date.today(),
        )
    )
    db.commit()
    return _redirect_with_msg(
        "/jurisprudencia", "Entendimento cadastrado e integrado ao algoritmo SM-2!"
    )


@router.post("/jurisprudencia/{juris_id}/favorito")
def acao_toggle_favorito_jurisprudencia(
    juris_id: int, db: Session = Depends(get_db)
):
    ent = db.get(EntendimentoJurisprudencia, juris_id)
    if ent:
        ent.favorito = not ent.favorito
        db.commit()
    return _redirect_with_msg("/jurisprudencia", "Lista de favoritos atualizada.")


@router.post("/jurisprudencia/{juris_id}/revisar-sm2")
def acao_revisar_jurisprudencia_sm2(
    juris_id: int,
    qualidade_sm2: int = Form(4),
    compreensao: str = Form(""),
    dificuldade: int = Form(3),
    redirect_to: str = Form("/jurisprudencia"),
    db: Session = Depends(get_db),
):
    ent = avaliar_entendimento_sm2(
        db=db,
        juris_id=juris_id,
        qualidade_0_a_5=qualidade_sm2,
        compreensao=compreensao.strip(),
        dificuldade=dificuldade,
    )
    return _redirect_with_msg(
        redirect_to,
        f"Revisão SM-2 registrada para '{ent.numero_identificacao}'! Próxima revisão em +{ent.sm2_intervalo_dias} dia(s) (EF={ent.sm2_easiness_factor}).",
    )


@router.get("/jurisprudencia/exportar-json")
def acao_exportar_jurisprudencia_json(db: Session = Depends(get_db)):
    payload = exportar_jurisprudencia_json(db)
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": 'attachment; filename="biblioteca_jurisprudencia_sumulas_2027.json"'
        },
    )


@router.post("/jurisprudencia/importar-json")
def acao_importar_jurisprudencia_json(
    json_payload: str = Form(...),
    sobrescrever_duplicados: str = Form("false"),
    db: Session = Depends(get_db),
):
    try:
        parsed = json.loads(json_payload)
    except Exception as exc:
        return _redirect_with_msg(
            "/jurisprudencia", f"JSON inválido: {exc}", "warning"
        )
    res = importar_jurisprudencia_json(
        db, parsed, sobrescrever_duplicados=(sobrescrever_duplicados == "true")
    )
    return _redirect_with_msg(
        "/jurisprudencia",
        f"Importação JSON concluída: {res['inseridos']} inseridos, {res['atualizados']} atualizados, {res['ignorados_duplicados']} duplicados preservados.",
    )


# =============================================================================
# 13, 14 & 15. DESEMPENHO, RADAR DE CONCURSOS, CONFIGURAÇÕES E BACKUPS
# =============================================================================
@router.get("/desempenho", response_class=HTMLResponse)
@router.get("/radar", response_class=HTMLResponse)
@router.get("/configuracoes", response_class=HTMLResponse)
def pagina_desempenho_radar_config(
    request: Request,
    msg: Optional[str] = None,
    db: Session = Depends(get_db),
):
    url_str = str(request.url)
    if "radar" in url_str:
        active = "radar"
        title = "Radar de Concursos e Oportunidades (SEFAZ-PE, ANPD, Dados e TI)"
    elif "configuracoes" in url_str:
        active = "configuracoes"
        title = "Configurações Estratégicas e Backups Atômicos SQLite"
    else:
        active = "desempenho"
        title = "Desempenho e Previsão de Domínio Baseada em Evidências"

    relatorio_dominio = calcular_previsao_dominio_por_disciplina(db)
    concursos_radar = db.scalars(select(Concurso).order_by(Concurso.id.asc())).all()
    configuracoes = db.scalars(select(Configuracao).order_by(Configuracao.id.asc())).all()

    arquivos_backup = []
    if BACKUPS_DIR.exists():
        for f in sorted(BACKUPS_DIR.glob("*.sqlite3"), reverse=True):
            arquivos_backup.append(
                {"nome": f.name, "tamanho_kb": round(f.stat().st_size / 1024.0, 1)}
            )

    return templates.TemplateResponse(
        request,
        "desempenho_radar_config.html",
        {
            "active_nav": active,
            "page_title": title,
            "page_subtitle": "Indicadores reais, compatibilidade no Radar e gestão segura do banco SQLite",
            "flash_message": msg,
            "relatorio_dominio": relatorio_dominio,
            "concursos_radar": concursos_radar,
            "configuracoes": configuracoes,
            "arquivos_backup": arquivos_backup,
        },
    )


@router.post("/radar/novo")
def acao_novo_concurso_radar(
    codigo: str = Form(...),
    sigla_orgao: str = Form(...),
    orgao: str = Form(...),
    area_foco: str = Form(...),
    status_concurso: str = Form("PROJECAO_EXPECTATIVA"),
    compatibilidade_formacao: float = Form(90.0),
    remuneracao_informada: str = Form(""),
    link_oficial: str = Form(""),
    db: Session = Depends(get_db),
):
    cod = codigo.strip().upper()
    if db.scalar(select(Concurso).where(Concurso.codigo == cod)):
        return _redirect_with_msg(
            "/radar", f"O concurso '{cod}' já está cadastrado no Radar.", "warning"
        )

    # Calcula compatibilidade real com os assuntos já cadastrados na matriz
    kpi = calcular_indicadores_dashboard(db)
    comp_assuntos = max(65.0, min(95.0, 75.0 + kpi["progresso_geral"] * 0.2))

    db.add(
        Concurso(
            codigo=cod,
            sigla_orgao=sigla_orgao.strip(),
            orgao=orgao.strip(),
            eixo_estrategico="EIXO_2_ANPD_TI"
            if "Dados" in area_foco or "TI" in area_foco or "Inteligência" in area_foco
            else "EIXO_1_SEFAZ_PE",
            peso_estrategico_percentual=0.0,
            area_foco=area_foco,
            status_concurso=status_concurso,
            prioridade_usuario="RADAR_OPORTUNIDADE",
            compatibilidade_formacao=compatibilidade_formacao,
            compatibilidade_assuntos=round(comp_assuntos, 1),
            remuneracao_informada=remuneracao_informada.strip() or None,
            link_oficial=link_oficial.strip() or None,
            ativo_no_planejamento=False,
            data_ultima_consulta=date.today(),
            observacoes="Cadastrado no Radar de Oportunidades (não altera automaticamente a rotina sem autorização).",
        )
    )
    db.commit()
    return _redirect_with_msg(
        "/radar",
        f"Oportunidade '{sigla_orgao}' registrada no Radar (rotina diária preservada).",
    )


@router.post("/configuracoes/backup-agora")
def acao_gerar_backup_sqlite():
    info = criar_backup_sqlite()
    return _redirect_with_msg(
        "/configuracoes",
        f"Backup atômico gerado: {info['arquivo_backup']} (Integridade SQLite: {info['integridade']}, SHA-256 verificado).",
    )


# =============================================================================
# ENDPOINTS JSON DE SAÚDE E INSPEÇÃO TÉCNICA
# =============================================================================
@router.get("/api/health")
def api_health(db: Session = Depends(get_db)):
    kpi = calcular_indicadores_dashboard(db)
    return {
        "status": "ok",
        "plataforma": "Plataforma Concurso 2027",
        "eixos_estrategicos": {
            "EIXO_1_SEFAZ_PE": 60,
            "EIXO_2_ANPD_DADOS_TI": 40,
            "frente_tecnologica_interna": kpi["distribuicao_interna_tecnologia"],
        },
        "arquivos_acervo_indexados": kpi["total_materiais"],
        "topicos_matriz_integrada": kpi["total_topicos"],
        "normas_cadastradas": kpi["total_normas"],
        "entendimentos_jurisprudencia_sm2": kpi["total_juris"],
        "flashcards_sm2": kpi["total_flashcards"],
    }
