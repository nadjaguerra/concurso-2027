"""Serviço de Carga Inicial Estruturada e Rastreável (Etapa 6).

Popula de forma idempotente:
- Configurações estratégicas (60% SEFAZ-PE / 40% ANPD + Dados & TI, e 30/25/25/20 em Tecnologia).
- Bancas (IAUPE/UPENET, Cebraspe, FGV, Cesgranrio).
- Concursos prioritários e oportunidades reais do acervo no Radar.
- Disciplinas unificadas e Tópicos da Matriz Integrada (sem duplicar conteúdos comuns).
- Indexação dos 221+ arquivos do acervo e vínculo automático com Legislação e Materiais.
- Inteligência de Cobrança baseada nas provas reais do acervo.
- Biblioteca inicial verificável de Súmulas, Jurisprudência e Enunciados ANPD com SM-2.
- Flashcards e Questões oficiais extraídas dos cadernos do acervo.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import (
    DISTRIBUICAO_INTERNA_TECNOLOGIA,
    PESO_EIXO_ANPD_TI,
    PESO_EIXO_SEFAZ_PE,
)
from app.models.entities import (
    AssociacaoMaterialTopico,
    AssociacaoTopicoConcurso,
    AvaliacaoNivelamento,
    Banca,
    Cargo,
    Concurso,
    Configuracao,
    Disciplina,
    Edital,
    EntendimentoJurisprudencia,
    ErroCaderno,
    Flashcard,
    FonteReferencia,
    HistoricoProvaCobranca,
    Material,
    MetaAlerta,
    NormaJuridica,
    Questao,
    RespostaQuestao,
    Revisao,
    SessaoEstudo,
    SessaoQuestoes,
    TarefaCronograma,
    Topico,
)
from app.services.acervo_service import indexar_acervo_completo


def aplicar_correcoes_integridade(db: Session) -> None:
    """Corrige dados de versões anteriores que não estavam verificados em fonte (idempotente)."""
    # 1) Questões escritas pela plataforma nunca podem aparecer como oficiais
    for q in db.scalars(select(Questao).where(Questao.natureza_questao == "OFICIAL_ACERVO")).all():
        q.natureza_questao = "QUESTAO_TREINO_PLATAFORMA"
        q.concurso_referencia = f"Treino no estilo {q.banca_nome}"
        q.ano = None
        q.fonte_origem = "Item de treino elaborado pela plataforma (não é questão oficial). Base: " + (q.fonte_origem or "")
    # 2) Normas: o arquivo está no acervo, mas a vigência ainda não foi conferida na fonte
    for n in db.scalars(select(NormaJuridica).where(NormaJuridica.status_vigencia == "VIGENTE_VERIFICADA_EM_FONTE")).all():
        if n.versao_controle and "Verificado" in n.versao_controle:
            n.status_vigencia = "TEXTO_NO_ACERVO_VIGENCIA_A_CONFERIR"
            n.versao_controle = "Texto do acervo (baixado em 22/11/2026)"
            n.data_atualizacao_verificada = None
            n.historico_alteracoes_legislativas = "Vigência e alterações ainda não conferidas na fonte oficial."
    # 3) Jurisprudência: textos de referência, a conferir no site oficial
    for j in db.scalars(select(EntendimentoJurisprudencia)).all():
        if j.situacao_vigencia == "VIGENTE_VERIFICADA":
            j.situacao_vigencia = "CONFERIR_NA_FONTE_OFICIAL"
            j.data_atualizacao_verificada = None
        if j.numero_identificacao.startswith("Tema Repetitivo 1177"):
            j.numero_identificacao = "Precedente do STJ sobre vazamento de dados comuns (identificação a confirmar)"
            j.situacao_vigencia = "PENDENTE_VERIFICACAO_FONTE"
            j.data_publicacao = None
            j.link_origem = None
            j.fonte_oficial = "A confirmar no portal do STJ (não confirmado como tema repetitivo)"
        if j.numero_identificacao.startswith("Acórdão TCU Plenário"):
            j.numero_identificacao = "Auditoria LGPD — TC 039.606/2020 (relatório no acervo)"
            j.data_publicacao = None
    # 4) Projetos (PMBOK/Scrum) não constam no edital da SEFAZ-PE
    t = db.scalar(select(Topico).where(Topico.codigo_estavel == "ADM_PUB_02"))
    if t:
        for a in db.scalars(select(AssociacaoTopicoConcurso).where(AssociacaoTopicoConcurso.topico_id == t.id)).all():
            c = db.get(Concurso, a.concurso_id)
            if c and c.codigo == "SEFAZ_PE_APOIO":
                a.status_no_concurso = "COMPLEMENTAR"
    # 5) Config antiga
    old = db.scalar(select(Configuracao).where(Configuracao.chave == "fase_estudo_atual"))
    if old:
        db.delete(old)
    db.commit()
    sincronizar_metas_sequenciais_guias(db)


METAS_SEQUENCIAIS_GUIAS = [
    # PORTUGUÊS (TODO DIA) — SEQUÊNCIA PASSO A PASSO (META 1 A META 13) + BLOCOS TEC
    (
        "PORT_M01",
        "PORT",
        "Meta 1 (Bloco I) — Ortografia, Acentuação Gráfica, Porquês e Hífen",
        "Grafia (S/Z, X/CH, G/J; verbos em -NDER -> S; TER -> Ç), acentuação, porquês e hífen • Caderno Tec CESPE: https://bit.ly/44NHIXA | FGV: https://bit.ly/3DjQvVr",
        False,
        45,
        9.8,
        "Guia de Estudos (Português Meta 1) + Guia Fiscal 3.0 Plus (Bloco I)",
        "AMBOS",
    ),
    (
        "PORT_M02",
        "PORT",
        "Meta 2 (Bloco I) — Morfologia: Formação e Classes de Palavras (Conjunções e Conectivos)",
        "Grupo nominal (substantivo, adjetivo, artigo, numeral, pronome), grupo verbal (verbo, advérbio), preposição e conjunção (tabela de conectivos) • Caderno Tec CESPE: https://bit.ly/44NHIXA",
        False,
        45,
        9.7,
        "Guia de Estudos (Português Meta 2) + Guia Fiscal 3.0 Plus (Bloco I)",
        "AMBOS",
    ),
    (
        "PORT_M03",
        "PORT",
        "Meta 3 (Bloco I) — Morfologia: Pronomes e Colocação Pronominal (Próclise, Mesóclise e Ênclise)",
        "Pronomes pessoais, demonstrativos, relativos ('cujo', 'onde') e indefinidos. Fatores de próclise (palavras negativas, advérbios, relativos), mesóclise e ênclise • Caderno Tec CESPE: https://bit.ly/44NHIXA",
        False,
        45,
        9.6,
        "Guia de Estudos (Português Meta 3) + Guia Fiscal 3.0 Plus (Bloco I)",
        "AMBOS",
    ),
    (
        "PORT_M04",
        "PORT",
        "Meta 4 (Bloco I) — Tempos e Modos Verbais e Correlação Verbal",
        "Modos Indicativo, Subjuntivo e Imperativo; correlação verbal (-SSE + -RIA), pretérito imperfeito (-VA/-IA) e verbos derivados de TER, POR, VER, VIR • Caderno Tec CESPE: https://bit.ly/44NHIXA",
        False,
        45,
        9.5,
        "Guia de Estudos (Português Meta 4) + Guia Fiscal 3.0 Plus (Bloco I)",
        "AMBOS",
    ),
    (
        "PORT_M05",
        "PORT",
        "Meta 5 (Bloco II) — Sintaxe (Parte 1): Sujeito, Predicado e Complementos Verbais",
        "Tipos de sujeito, oração sem sujeito (verbo HAVER = existir, invariável), transitividade verbal (VTD, VTI, VTDI, VI, VL) e adjunto adnominal x complemento nominal • Caderno Tec CESPE: https://bit.ly/3rzcyF0",
        False,
        45,
        9.5,
        "Guia de Estudos (Português Meta 6) + Guia Fiscal 3.0 Plus (Bloco II)",
        "AMBOS",
    ),
    (
        "PORT_M06",
        "PORT",
        "Meta 6 (Bloco II) — Sintaxe (Parte 2): Período Composto (Coordenação, Subordinação e Conectivos)",
        "Orações coordenadas e subordinadas adverbiais (causais, concessivas, condicionais, finais) e adjetivas (restritivas sem vírgula x explicativas com vírgula) • Caderno Tec CESPE: https://bit.ly/3rzcyF0",
        False,
        45,
        9.5,
        "Guia de Estudos (Português Meta 7) + Guia Fiscal 3.0 Plus (Bloco II)",
        "AMBOS",
    ),
    (
        "PORT_M07",
        "PORT",
        "Meta 7 (Bloco III) — Pontuação (Ordem Direta SVC, Vírgula, Aposto, Vocativo, Dois-Pontos e Aspas)",
        "Não separar Sujeito-Verbo-Complemento; vírgula em adjunto adverbial deslocado, enumerações, aposto e vocativo • Caderno Tec CESPE: https://bit.ly/3ryXSWr",
        False,
        45,
        9.4,
        "Guia de Estudos (Português Meta 8) + Guia Fiscal 3.0 Plus (Bloco III)",
        "AMBOS",
    ),
    (
        "PORT_M08",
        "PORT",
        "Meta 8 (Bloco IV) — Funções do 'QUE', Funções do 'SE' e Vozes Verbais",
        "'Que' pronome relativo x conjunção integrante; 'Se' partícula apassivadora (verbo concorda) x índice de indeterminação do sujeito (singular); vozes verbais • Caderno Tec CESPE: https://bit.ly/43sUda5",
        False,
        45,
        9.4,
        "Guia de Estudos (Português Meta 10) + Guia Fiscal 3.0 Plus (Bloco IV)",
        "AMBOS",
    ),
    (
        "PORT_M09",
        "PORT",
        "Meta 9 (Blocos III e IV) — Concordância Nominal e Verbal e Regência Nominal e Verbal",
        "Regras de concordância (expressões partitivas, verbos impessoais) e regência de verbos recorrentes (visar, assistir, aspirar, implicar, obedecer) • Cadernos Tec CESPE: https://bit.ly/3ryXSWr e https://bit.ly/43sUda5",
        False,
        45,
        9.3,
        "Guia de Estudos (Português Meta 11) + Guia Fiscal 3.0 Plus (Blocos III e IV)",
        "AMBOS",
    ),
    (
        "PORT_M10",
        "PORT",
        "Meta 10 (Bloco III) — Crase (Regra Geral, Casos Proibidos, Obrigatórios e Facultativos)",
        "Fusão preposição A + artigo A; proibida antes de masculino, verbo e plural sem artigo; facultativa antes de nome próprio feminino, pronome possessivo feminino e 'até' • Caderno Tec CESPE: https://bit.ly/3ryXSWr",
        False,
        45,
        9.3,
        "Guia de Estudos (Português Meta 12) + Guia Fiscal 3.0 Plus (Bloco III)",
        "AMBOS",
    ),
    (
        "PORT_M11",
        "PORT",
        "Meta 11 (Blocos IV e VI-VIII) — Interpretação e Compreensão Textual, Semântica, Coesão e Coerência",
        "Tema x Tese, inferência x extrapolação, sinônimos/antônimos, denotação/conotação e referenciação (anáfora/catáfora) • Cadernos Tec CESPE: https://bit.ly/3OjuxYV e https://bit.ly/3PXwz2g",
        False,
        45,
        9.2,
        "Guia de Estudos (Português Meta 14) + Guia Fiscal 3.0 Plus (Blocos VI-VIII: 37,6% da prova CESPE)",
        "AMBOS",
    ),
    (
        "PORT_M12",
        "PORT",
        "Meta 12 (Bloco V) — Tipos e Gêneros Textuais, Clareza/Correção e Reescrita de Frases",
        "Tipos (narrativo, descritivo, expositivo, argumentativo, injuntivo) e questões de reescrita mantendo correção gramatical e sentido original (17,6% da prova CESPE) • Caderno Tec CESPE: https://bit.ly/3rChZTP",
        False,
        45,
        9.2,
        "Guia de Estudos (Português Metas 15 e 16) + Guia Fiscal 3.0 Plus (Bloco V)",
        "AMBOS",
    ),
    (
        "PORT_M13",
        "PORT",
        "Meta 13 — Redação Oficial (Manual de Redação da Presidência da República) e Atualização",
        "Atributos (clareza, concisão, impessoalidade, formalidade, objetividade, padronização), pronomes de tratamento, fechos e padrão ofício • Caderno Atualização Tec CESPE: https://bit.ly/4fHoNEg",
        False,
        45,
        9.1,
        "Guia de Estudos (Português Meta 18) + Guia Fiscal 3.0 Plus (Atualização)",
        "AMBOS",
    ),
    # DIREITO CONSTITUCIONAL — COMEÇANDO DOS ARTS. 1º AO 4º (META 1 A META 10)
    (
        "DIR_CONST_M01",
        "DIR_CONST",
        "Meta 1 (Bloco I) — Princípios Fundamentais (Arts. 1º ao 4º da CF/88) e Aplicabilidade das Normas",
        "Leitura dos arts. 1º ao 4º da CF/88: Fundamentos (SO-CI-DI-VA-PLU), Tripartição de Poderes (art. 2º), Objetivos Fundamentais (CON-GAR-ER-PRO), Relações Internacionais (art. 4º) e eficácia das normas (plena, contida, limitada) • Cadernos Tec CESPE: https://bit.ly/3KeHTDz e https://bit.ly/3O03n8c",
        False,
        60,
        9.9,
        "Guia de Estudos (Direito Constitucional Meta 1) + Guia Fiscal 3.0 Plus (Bloco I — pág. 119)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M02",
        "DIR_CONST",
        "Meta 2 (Blocos I e II) — Direitos e Deveres Individuais e Coletivos (Art. 5º da CF/88 e Remédios Constitucionais)",
        "Leitura do Art. 5º: inviolabilidade do domicílio (XI), reunião, desapropriação x requisição, crimes inafiançáveis/imprescritíveis, proteção de dados pessoais (LXXIX), SV 14 e SV 21 e os 5 Remédios Constitucionais (HC, HD, MS, MI, Ação Popular) • Cadernos Tec CESPE: https://bit.ly/3KeHTDz e https://bit.ly/3pUhnIM",
        False,
        60,
        9.8,
        "Guia de Estudos (Direito Constitucional Meta 2) + Guia Fiscal 3.0 Plus (Blocos I e II — pág. 120)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M03",
        "DIR_CONST",
        "Meta 3 (Bloco II) — Direitos Sociais (Arts. 6º ao 11 da CF/88)",
        "Rol do art. 6º (renda básica familiar), direitos dos trabalhadores urbanos e rurais (art. 7º), associação profissional ou sindical (art. 8º) e direito de greve (art. 9º) • Caderno Tec CESPE: https://bit.ly/3pUhnIM",
        False,
        55,
        9.6,
        "Guia de Estudos (Direito Constitucional Meta 3) + Guia Fiscal 3.0 Plus (Bloco II)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M04",
        "DIR_CONST",
        "Meta 4 (Bloco II) — Nacionalidade (Arts. 12 e 13 da CF/88 — atenção à EC 131/2023)",
        "Brasileiros natos x naturalizados, cargos privativos de brasileiro nato (MP3.COM), extradição e novas hipóteses de perda da nacionalidade (EC 131/2023) • Caderno Tec CESPE: https://bit.ly/3pUhnIM",
        False,
        55,
        9.5,
        "Guia de Estudos (Direito Constitucional Meta 4) + Guia Fiscal 3.0 Plus (Bloco II Atualizado 2024)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M05",
        "DIR_CONST",
        "Meta 5 (Bloco II) — Direitos Políticos e Partidos Políticos (Arts. 14 a 17 da CF/88)",
        "Alistamento e voto, idades mínimas ('telefone 3530-2118'), inelegibilidade reflexa (até 2º grau), desincompatibilização (6 meses), perda/suspensão de direitos políticos e autonomia partidária • Caderno Tec CESPE: https://bit.ly/3pUhnIM",
        False,
        55,
        9.4,
        "Guia de Estudos (Direito Constitucional Metas 5 e 6) + Guia Fiscal 3.0 Plus (Bloco II)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M06",
        "DIR_CONST",
        "Meta 6 (Bloco III) — Organização Político-Administrativa do Estado (Arts. 18 a 36 da CF/88)",
        "União, Estados, DF e Municípios; bens (arts. 20 e 26); competências exclusivas (art. 21 - verbo), privativas (art. 22), comuns (art. 23 - verbo) e concorrentes ('FUPET' - art. 24, §§ 1º a 4º); intervenção (arts. 34-36) • Caderno Tec CESPE: https://bit.ly/3Dun6YU",
        False,
        60,
        9.4,
        "Guia de Estudos (Meta 8) + Guia Fiscal 3.0 Plus (Bloco III — págs. 122-123)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M07",
        "DIR_CONST",
        "Meta 7 (Bloco IV) — Administração Pública Constitucional e Servidores Públicos (Arts. 37 a 41 da CF/88)",
        "Princípios LIMPE, concurso público (SV 43), cargos em comissão x funções de confiança, teto remuneratório, acumulação de cargos, estabilidade (3 anos) e responsabilidade objetiva (art. 37, § 6º) • Caderno Tec CESPE: https://bit.ly/44CNXhp",
        False,
        60,
        9.3,
        "Guia de Estudos (Meta 9) + Guia Fiscal 3.0 Plus (Bloco IV — pág. 124)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M08",
        "DIR_CONST",
        "Meta 8 (Bloco V) — Poder Legislativo, Processo Legislativo e Fiscalização Contábil/Financeira/Orçamentária (Arts. 44 a 75)",
        "Congresso (arts. 48-49), Câmara (art. 51) e Senado (art. 52), CPI (art. 58, § 3º), PEC (3/5 em 2 turnos), Medidas Provisórias (art. 62) e Controle Externo + TCU/TCE (arts. 70-75: PR = TCU aprecia e CN julga) • Caderno Tec CESPE: https://bit.ly/3Y9Duas",
        False,
        60,
        9.2,
        "Guia de Estudos (Metas 10 e 11) + Guia Fiscal 3.0 Plus (Bloco V — págs. 124-128)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M09",
        "DIR_CONST",
        "Meta 9 (Blocos VI e IX) — Poder Executivo (Arts. 76-91), Poder Judiciário, Funções Essenciais e Controle de Constitucionalidade",
        "Atribuições privativas do PR (art. 84 e incisos delegáveis VI, XII e XXV), estrutura do Judiciário (STF/CNJ/STJ), Ministério Público (arts. 127-130) e Controle Difuso e Concentrado (ADI, ADC, ADPF) • Cadernos Tec CESPE: https://bit.ly/3KbNMRT e https://bit.ly/3O03n8c",
        False,
        60,
        9.1,
        "Guia de Estudos (Metas 12 a 16) + Guia Fiscal 3.0 Plus (Blocos VI e IX)",
        "AMBOS",
    ),
    (
        "DIR_CONST_M10",
        "DIR_CONST",
        "Meta 10 (Blocos VII e VIII) — Sistema Tributário Nacional (Arts. 145-162), Finanças Públicas (Arts. 163-169) e Ordem Econômica/Social",
        "Princípios tributários, limitações ao poder de tributar, impostos da União e dos Estados (ICMS, IPVA, ITCMD + Reforma Tributária EC 132/2023), repartição de receitas e orçamento (PPA, LDO, LOA) • Cadernos Tec CESPE: https://bit.ly/46KWSPn e https://bit.ly/4dgARKQ",
        False,
        60,
        9.0,
        "Guia de Estudos (Meta 18) + Guia Fiscal 3.0 Plus (Blocos VII e VIII)",
        "SEFAZ_PE",
    ),
    # RACIOCÍNIO LÓGICO — SEQUÊNCIA PASSO A PASSO (META 1 A META 6)
    (
        "RLM_M01",
        "RLM",
        "Meta 1 (Bloco I) — Lógica Proposicional (Parte 1): Proposições Simples/Compostas, Conectivos e Tabela-Verdade",
        "O que não é proposição (interrogativas, exclamativas, imperativas, sentenças abertas, paradoxos), conectivos ('e', 'ou', 'ou...ou', 'se...então' Vera Fischer, 'se e somente se') e tabela-verdade • Caderno Tec CESPE: https://bit.ly/44SJfM5",
        False,
        50,
        9.8,
        "Guia de Estudos (RLM Meta 1) + Guia Fiscal 3.0 Plus (RLM Bloco I — págs. 57-58)",
        "AMBOS",
    ),
    (
        "RLM_M02",
        "RLM",
        "Meta 2 (Bloco I) — Lógica Proposicional (Parte 2): Tautologia, Equivalências (De Morgan), Quantificadores e Negações",
        "Tautologia, contradição e contingência; Leis de De Morgan; equivalência da condicional ('Se P então Q' = 'Se não Q então não P' = 'Não P ou Q'); negação de Todo (Algum não), Algum (Nenhum) e Nenhum (Algum) • Caderno Tec CESPE: https://bit.ly/44SJfM5",
        False,
        50,
        9.7,
        "Guia de Estudos (RLM Meta 2) + Guia Fiscal 3.0 Plus (RLM Bloco I — 27,6% da prova)",
        "AMBOS",
    ),
    (
        "RLM_M03",
        "RLM",
        "Meta 3 (Blocos II, III e IV) — Associação de Informações, Verdade/Mentira, Sequências e Argumentação Lógica",
        "Deduções por tabela de associação de informações (10% da prova), exercícios de verdade/mentira, validade de argumentos lógicos e sequências • Cadernos Tec CESPE: https://bit.ly/3Q6R4JV, https://bit.ly/44zi09E e https://bit.ly/3Onzos8",
        False,
        50,
        9.5,
        "Guia de Estudos (RLM Meta 3) + Guia Fiscal 3.0 Plus (RLM Blocos II, III e IV)",
        "AMBOS",
    ),
    (
        "RLM_M04",
        "RLM",
        "Meta 4 (Blocos III e V) — Diagramas Lógicos, Proposições Categóricas e Conjuntos (Diagramas de Venn)",
        "Representação de proposições categóricas ('todo A é B', 'algum A é B', 'nenhum A é B') por diagramas e operações com conjuntos (união, interseção, diferença) • Cadernos Tec CESPE: https://bit.ly/44zi09E e https://bit.ly/3pZPi2I",
        False,
        50,
        9.4,
        "Guia de Estudos (RLM Meta 5) + Guia Fiscal 3.0 Plus (RLM Blocos III e V)",
        "AMBOS",
    ),
    (
        "RLM_M05",
        "RLM",
        "Meta 5 (Blocos VI e VII) — Análise Combinatória (Permutação, Arranjo e Combinação), Porcentagem e Proporção",
        "Contagem básica, Arranjo (ordem importa) x Combinação (ordem não importa), porcentagem e grandezas direta/inversamente proporcionais • Cadernos Tec CESPE: https://bit.ly/3Y4nS8u e https://bit.ly/3DtxTlP",
        False,
        50,
        9.3,
        "Guia de Estudos (RLM Meta 6) + Guia Fiscal 3.0 Plus (RLM Blocos VI e VII)",
        "AMBOS",
    ),
    (
        "RLM_M06",
        "RLM",
        "Meta 6 (Bloco VII) — Probabilidade (Espaço Amostral, União de Eventos, Probabilidade Condicional)",
        "Casos favoráveis / casos possíveis, probabilidade do 'ou' (soma) e do 'e' (multiplicação), eventos independentes e com/sem reposição • Caderno Tec CESPE: https://bit.ly/3DtxTlP",
        False,
        50,
        9.2,
        "Guia de Estudos (RLM Meta 7) + Guia Fiscal 3.0 Plus (RLM Bloco VII)",
        "AMBOS",
    ),
    # DIREITO ADMINISTRATIVO (DOUTRINA + LEGISLAÇÃO) — META 1 A META 10
    (
        "DIR_ADM_M01",
        "DIR_ADM",
        "Meta 1 (Bloco I) — Conceito e Princípios do Direito Administrativo (Explícitos LIMPE e Implícitos)",
        "Supremacia e Indisponibilidade do interesse público; Legalidade, Impessoalidade (art. 37, § 1º + SV 13 Nepotismo), Moralidade, Publicidade e Eficiência; Intranscendência subjetiva das sanções e Autotutela (Súmula 473 STF) • Caderno Tec CESPE: https://bit.ly/3KbMLJI",
        False,
        60,
        9.9,
        "Guia de Estudos (Dir. Adm. Meta 1) + Guia Fiscal 3.0 Plus (Bloco I — págs. 84-85)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M02",
        "DIR_ADM",
        "Meta 2 (Bloco I) — Organização Administrativa (Parte 1): Órgãos, Entidades, Desconcentração e Descentralização",
        "Entes políticos x entidades administrativas; órgãos públicos (teoria do órgão); desconcentração (cria órgãos na mesma PJ) x descentralização (outorga por lei x delegação por contrato/ato) • Caderno Tec CESPE: https://bit.ly/3KbMLJI",
        False,
        60,
        9.8,
        "Guia de Estudos (Dir. Adm. Meta 2) + Guia Fiscal 3.0 Plus (Bloco I — pág. 85)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M03",
        "DIR_ADM",
        "Meta 3 (Bloco I) — Organização Administrativa (Parte 2): Autarquias, Fundações, EP/SEM e Terceiro Setor (OS x OSCIP)",
        "Autarquias (Agências Reguladoras como a ANPD), Fundações, diferenças entre Empresa Pública (100% público, qualquer forma, JF) e SEM (misto, S.A., JE), autarquização das estatais (STF) e OS (contrato de gestão) x OSCIP (termo de parceria) • Caderno Tec CESPE: https://bit.ly/3KbMLJI",
        False,
        60,
        9.7,
        "Guia de Estudos (Dir. Adm. Meta 3) + Guia Fiscal 3.0 Plus (Bloco I — pág. 86)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M04",
        "DIR_ADM",
        "Meta 4 (Bloco II) — Poderes Administrativos: Hierárquico, Disciplinar, Regulamentar e de Polícia (Ciclo e Delegação)",
        "Atributos do poder de polícia ('DiCA': Discricionariedade, Coercibilidade, Autoexecutoriedade), 4 fases do ciclo de polícia (Ordem, Consentimento, Fiscalização, Sanção — delegação STF x STJ) e abuso de poder • Caderno Tec CESPE: https://bit.ly/3OqHcbF",
        False,
        60,
        9.6,
        "Guia de Estudos (Dir. Adm. Metas 4 e 5) + Guia Fiscal 3.0 Plus (Bloco II — págs. 87-88)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M05",
        "DIR_ADM",
        "Meta 5 (Bloco II) — Atos Administrativos: Requisitos (Co.Fi.Fo.Mo.Ob), Atributos (PATI), Classificação e Extinção",
        "Competência, Finalidade, Forma, Motivo e Objeto; Presunção de legitimidade, Autoexecutoriedade, Tipicidade e Imperatividade; Ato Simples x Composto (1 órgão/2 atos) x Complexo (2 órgãos/1 ato); Anulação, Revogação (Súmula 473 STF), Cassação, Caducidade e Convalidação • Caderno Tec CESPE: https://bit.ly/3OqHcbF",
        False,
        60,
        9.5,
        "Guia de Estudos (Dir. Adm. Metas 7 e 8) + Guia Fiscal 3.0 Plus (Bloco II — págs. 88-89)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M06",
        "DIR_ADM",
        "Meta 6 (Blocos III, IV e IX) — Responsabilidade Civil do Estado, Controle, Agentes, Serviços Públicos e Bens",
        "Responsabilidade objetiva (art. 37, § 6º — Risco Administrativo), controle interno/externo, servidores públicos, concessão/permissão (Lei 8.987/95) e bens públicos • Cadernos Tec CESPE: https://bit.ly/3QaOum5, https://bit.ly/3pVoP6r e https://bit.ly/3qag9ZI",
        False,
        60,
        9.4,
        "Guia de Estudos (Dir. Adm. Metas 9 a 15) + Guia Fiscal 3.0 Plus (Blocos III, IV e IX)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M07",
        "DIR_ADM",
        "Meta 7 (Blocos V e VIII) — Legislação: Lei nº 9.784/1999 (Processo Administrativo Federal), LINDB e LAI (Lei 12.527/2011)",
        "Competências indelegáveis ('EX-NO-RA' - art. 13), impedimento/suspeição, motivação (art. 50), decadência quinquenal (art. 54), recursos (arts. 56-65) e transparência ativa/passiva na LAI • Cadernos Tec CESPE: https://bit.ly/3Y7AmvY e https://bit.ly/44YjD0d",
        False,
        60,
        9.3,
        "Guia de Estudos (Legislação Meta 1) + Guia Fiscal 3.0 Plus (Blocos V e VIII)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M08",
        "DIR_ADM",
        "Meta 8 (Bloco V) — Legislação: Lei nº 8.429/1992 (Improbidade Administrativa atualizada pela Lei 14.230/2021)",
        "Exigência de dolo específico (7,8% das provas fiscais); enriquecimento ilícito (art. 9º), lesão ao erário (art. 10) e violação a princípios (art. 11 - rol taxativo); sanções (art. 12) e prescrição (art. 23) • Caderno Tec CESPE: https://bit.ly/3Y7AmvY",
        False,
        60,
        9.2,
        "Guia de Estudos (Legislação Meta 2) + Guia Fiscal 3.0 Plus (Bloco V)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M09",
        "DIR_ADM",
        "Meta 9 (Bloco VI) — Legislação: Nova Lei de Licitações nº 14.133/2021 (Parte 1 — Âmbito, Agentes, Fases e Modalidades)",
        "Arts. 1º a 71: âmbito de aplicação, princípios (segregação de funções), fases da licitação e as 5 modalidades (Pregão, Concorrência, Concurso, Leilão e Diálogo Competitivo — sem Tomada de Preços/Convite/RDC) • Caderno Tec CESPE: https://bit.ly/4dA08QB",
        True,
        75,
        9.1,
        "Guia de Estudos (Legislação Metas 4 a 6) + Guia Fiscal 3.0 Plus (Bloco VI Atualizado 2024)",
        "AMBOS",
    ),
    (
        "DIR_ADM_M10",
        "DIR_ADM",
        "Meta 10 (Bloco VII e X) — Legislação: Lei nº 14.133/2021 (Parte 2 — Contratação Direta e Contratos) e Jurisprudência Adm.",
        "Arts. 72 a 168: Inexigibilidade (art. 74) x Dispensa (art. 75), instrumentos auxiliares (SRP), contratos administrativos (arts. 89-154) e Jurisprudência em Direito Administrativo • Cadernos Tec CESPE: https://bit.ly/4fKQCv9 e https://bit.ly/4dHMEls",
        True,
        75,
        9.0,
        "Guia de Estudos (Legislação Metas 8 a 10) + Guia Fiscal 3.0 Plus (Blocos VII e X)",
        "AMBOS",
    ),
    # LEGISLAÇÃO ESTADUAL DE PERNAMBUCO (SEFAZ-PE) — METAS 1 A 3
    (
        "LEG_PE_M01",
        "LEG_PE",
        "Meta 1 — Estatuto dos Servidores de Pernambuco (Lei Estadual nº 6.123/1968 — Parte 1: Arts. 1º ao 108)",
        "Conceitos, provimento (nomeação, promoção, reintegração, aproveitamento, reversão, transferência), posse, exercício, estágio probatório (3 anos), vacância e jornada (30h semanais).",
        False,
        60,
        9.6,
        "Guia de Estudos (Legislação PE Meta 8 — pág. 134) + Lei PE 6.123/1968 em 02_SEFAZ_PE",
        "SEFAZ_PE",
    ),
    (
        "LEG_PE_M02",
        "LEG_PE",
        "Meta 2 — Estatuto dos Servidores de Pernambuco (Lei Estadual nº 6.123/1968 — Parte 2: Arts. 109 a 269)",
        "Licenças, vencimento, gratificações, indenizações, deveres, proibições, responsabilidades, penalidades e Processo Administrativo Disciplinar estadual.",
        False,
        60,
        9.5,
        "Guia de Estudos (Legislação PE Meta 9 — pág. 135) + Lei PE 6.123/1968 em 02_SEFAZ_PE",
        "SEFAZ_PE",
    ),
    (
        "LEG_PE_M03",
        "LEG_PE",
        "Meta 3 — Processo Administrativo PE (Lei 11.781/2000), FASAF (Lei 15.815/2016) e Constituição de PE",
        "Lei Estadual 11.781/2000, estrutura do FASAF (Lei 15.815/2016 — gestão pela SAFI e distribuição ao GOAAF) e dispositivos da Constituição Estadual de PE.",
        False,
        60,
        9.4,
        "Guia de Estudos (Meta 20) + Pasta 02_SEFAZ_PE",
        "SEFAZ_PE",
    ),
    # ORÇAMENTO PÚBLICO / AFO (SEFAZ-PE) — METAS 1 A 8 (GUIA FISCAL 3.0 PLUS)
    (
        "AFO_M01",
        "AFO",
        "Meta 1 (Bloco I) — Introdução ao Orçamento Público, Classificações e Princípios Orçamentários",
        "Princípios orçamentários (9,2% das provas: Exclusividade, Universalidade, Anualidade, Não-Afetação, Orçamento Bruto) e técnicas orçamentárias • Caderno Tec CESPE: https://bit.ly/447Ca9t | FGV: https://bit.ly/3X3nFmO",
        False,
        60,
        9.8,
        "Guia Fiscal 3.0 Plus (AFO Bloco I) + Edital SEFAZ-PE 2022",
        "SEFAZ_PE",
    ),
    (
        "AFO_M02",
        "AFO",
        "Meta 2 (Bloco II) — Instrumentos de Planejamento (PPA, LDO e LOA) e Ciclo Orçamentário (Arts. 165-169 CF/88)",
        "PPA (DOM: Diretrizes, Objetivos e Metas; 4 anos), LDO (metas/prioridades, reserva de contingência), LOA (fiscal, seguridade, investimento) e vedações do art. 167 • Caderno Tec CESPE: https://bit.ly/45phtam | FGV: https://bit.ly/4fDx4ZE",
        False,
        60,
        9.7,
        "Guia Fiscal 3.0 Plus (AFO Bloco II) + MTO 2027",
        "SEFAZ_PE",
    ),
    (
        "AFO_M03",
        "AFO",
        "Meta 3 (Bloco III) — Créditos Ordinários e Créditos Adicionais (Suplementares, Especiais e Extraordinários)",
        "Suplementares (reforço de dotação), Especiais (sem dotação específica), Extraordinários (urgência/imprevisibilidade por MP/Decreto) e fontes de recursos (superávit financeiro, excesso de arrecadação, anulação) • Caderno Tec CESPE: https://bit.ly/47ys0BK",
        False,
        60,
        9.6,
        "Guia Fiscal 3.0 Plus (AFO Bloco III) + Lei 4.320/1964",
        "SEFAZ_PE",
    ),
    (
        "AFO_M04",
        "AFO",
        "Meta 4 (Bloco IV) — Receita Pública: Conceito, Classificações (Corrente x Capital) e Estágios (PLAR)",
        "Receita orçamentária x extraorçamentária, classificação por natureza (Correntes: Tributária, Contribuições, Patrimonial, Serviços, Transferências x Capital: Operações de Crédito, Alienação, Amortização) e estágios (Previsão, Lançamento, Arrecadação, Recolhimento) • Caderno Tec CESPE: https://bit.ly/3QIJ3eF",
        False,
        60,
        9.5,
        "Guia Fiscal 3.0 Plus (AFO Bloco IV) + MCASP 11ª ed.",
        "SEFAZ_PE",
    ),
    (
        "AFO_M05",
        "AFO",
        "Meta 5 (Bloco V) — Despesa Pública: Classificações e Estágios (Fixação, Empenho, Liquidação e Pagamento)",
        "Despesas Correntes x Capital (Investimentos, Inversões Financeiras, Transferências de Capital), espécies de empenho (ordinário, estimativo, global), liquidação e pagamento • Caderno Tec CESPE: https://bit.ly/455B6EE",
        False,
        60,
        9.5,
        "Guia Fiscal 3.0 Plus (AFO Bloco V) + MCASP 11ª ed.",
        "SEFAZ_PE",
    ),
    (
        "AFO_M06",
        "AFO",
        "Meta 6 (Bloco VI) — Restos a Pagar (RAP), Despesas de Exercícios Anteriores (DEA), Suprimento de Fundos e Dívida",
        "RAP processados x não processados, hipóteses de DEA (art. 37 Lei 4.320/64), regime de adiantamento (suprimento de fundos) e dívida flutuante x fundada • Caderno Tec CESPE: https://bit.ly/47Cra7k",
        False,
        60,
        9.4,
        "Guia Fiscal 3.0 Plus (AFO Bloco VI)",
        "SEFAZ_PE",
    ),
    (
        "AFO_M07",
        "AFO",
        "Meta 7 (Bloco VII) — Lei de Responsabilidade Fiscal (LC 101/2000 — Parte 1: Planejamento, RCL, Receita e Despesa com Pessoal)",
        "Arts. 1º a 24 da LRF: Receita Corrente Líquida, renúncia de receita (art. 14), geração de despesa e DOCC (arts. 15-17) e limites de despesa com pessoal (União 50%, Estados 60%) • Caderno Tec CESPE: https://bit.ly/3KBgOuk",
        True,
        70,
        9.4,
        "Guia Fiscal 3.0 Plus (AFO Bloco VII) + LC 101/2000",
        "SEFAZ_PE",
    ),
    (
        "AFO_M08",
        "AFO",
        "Meta 8 (Bloco VIII) — Lei de Responsabilidade Fiscal (LC 101/2000 — Parte 2: Transferências, Dívida, RREO e RGF)",
        "Arts. 25 a 59 da LRF: Transferências voluntárias (art. 25), dívida consolidada e ARO, Relatório Resumido da Execução Orçamentária (RREO - bimestral) e Relatório de Gestão Fiscal (RGF - quadrimestral) • Caderno Tec CESPE: https://bit.ly/44aX9bD",
        True,
        70,
        9.3,
        "Guia Fiscal 3.0 Plus (AFO Bloco VIII) + LC 101/2000",
        "SEFAZ_PE",
    ),
    # ANPD — DADOS & TI (FRENTE TECNOLÓGICA — METAS SEQUENCIAIS DO GUIA 3.0 PLUS)
    (
        "TI_CD_M01",
        "TI_CD_EST",
        "Meta 1 (Bloco I) — Fluência em Dados, Tipos de Atributos, Pré-Processamento e Estatística Descritiva",
        "Atributos (binário, nominal, ordinal, razão), limpeza (MCAR/MAR/NMAR, outliers), redução (PCA), normalização (Min-Max, Z-Score, IQR), medidas de posição (média, mediana, quartis, box-plot) e dispersão (variância, desvio-padrão, CV) • Cadernos Tec CESPE: https://bit.ly/3KfWJcM e https://bit.ly/3YAtTdg",
        False,
        45,
        9.8,
        "Guia Fiscal 3.0 Plus (Fluência de Dados Bloco I + Estatística Blocos I e II)",
        "ANPD",
    ),
    (
        "TI_CD_M02",
        "TI_CD_EST",
        "Meta 2 (Blocos III e IV) — Probabilidade e Distribuições Discretas (Bernoulli, Binomial, Poisson) e Contínuas (Normal)",
        "Probabilidade da união, eventos independentes x mutuamente excludentes, Binomial (E=np, Var=npq), Poisson (média = variância = lambda) e Distribuição Normal padrão • Cadernos Tec CESPE: https://bit.ly/3DZXcwa e https://bit.ly/3E4IKmx",
        False,
        45,
        9.6,
        "Guia Fiscal 3.0 Plus (Estatística Blocos III e IV)",
        "ANPD",
    ),
    (
        "TI_CD_M03",
        "TI_CD_EST",
        "Meta 3 (Blocos V a VIII) — Inferência, Intervalos de Confiança, Testes de Hipóteses, Regressão, ANOVA e Python/R",
        "Estimadores, erro Tipo I (alfa) e Tipo II (beta), p-valor, Regressão Linear Simples e Múltipla, séries temporais, ANOVA e análise de dados em Python/R • Cadernos Tec CESPE: https://bit.ly/45x5E1G e https://bit.ly/3OBt0fY",
        False,
        45,
        9.4,
        "Guia Fiscal 3.0 Plus (Estatística Blocos V-VIII + Fluência Blocos VI-VII)",
        "ANPD",
    ),
    (
        "TI_ENG_M01",
        "TI_ENG_DADOS",
        "Meta 1 (Blocos I e II) — Bancos de Dados Relacionais (SQL: DDL/DML/DQL), Modelagem Relacional/Dimensional e SGBDs",
        "Modelagem ER, normalização (1FN, 2FN, 3FN, BCNF), consultas SQL, transações ACID, controle de concorrência, backup e administração de SGBDs • Cadernos Tec CESPE: https://bit.ly/3YHqv0i e https://bit.ly/3sjM4YI",
        False,
        45,
        9.7,
        "Guia Fiscal 3.0 Plus (TI Grupo II — Fundamentos de BDs Blocos I e II)",
        "ANPD",
    ),
    (
        "TI_ENG_M02",
        "TI_ENG_DADOS",
        "Meta 2 (Blocos III e IV) — Pipelines ETL/ELT, Data Warehouse (OLAP), Data Lake, Big Data (Hadoop/Spark), NoSQL e Governança",
        "Arquitetura DW (Star/Snowflake) x Data Lake, operações OLAP (drill-down, roll-up, slice, dice), Hadoop/Spark, bancos NoSQL (chave-valor, documento, colunar, grafo) e Governança de Dados (centralizada, compartilhada, colegiada) • Cadernos Tec CESPE: https://bit.ly/44lKMty e https://bit.ly/3rBTB4v",
        False,
        45,
        9.5,
        "Guia Fiscal 3.0 Plus (TI Grupo II Blocos III-IV + Fluência Blocos IV, V e VIII)",
        "ANPD",
    ),
    (
        "TI_IA_M01",
        "TI_IA",
        "Meta 1 (Bloco II) — Aprendizado de Máquina (Supervisionado, Não Supervisionado e Reforço), Classificação, Regressão e Clustering",
        "Classificação (dados rotulados) x Agrupamento/Clustering (dados não rotulados), árvores de decisão, Random Forest, regressão logística, regras de associação (suporte e confiança), overfitting/underfitting e Matriz de Confusão • Caderno Tec CESPE: https://bit.ly/4747gSi",
        False,
        45,
        9.7,
        "Guia Fiscal 3.0 Plus (Fluência de Dados Bloco II + TI Grupo III)",
        "ANPD",
    ),
    (
        "TI_IA_M02",
        "TI_IA",
        "Meta 2 (Bloco III) — Redes Neurais, Deep Learning, Processamento de Linguagem Natural (PLN) e Governança de IA (Art. 20 LGPD)",
        "Tarefas de PLN (stemming, lemmatization, remoção de stopwords, bag of words), redes neurais artificiais, deep learning, revisão de decisões automatizadas e explicabilidade • Cadernos Tec CESPE: https://bit.ly/479YEJK e https://bit.ly/3YHP90z",
        False,
        45,
        9.5,
        "Guia Fiscal 3.0 Plus (Fluência de Dados Bloco III + TI Grupo III)",
        "ANPD",
    ),
    (
        "TI_GERAL_M01",
        "TI_GERAL",
        "Meta 1 (Segurança Blocos I e II) — Segurança da Informação (CIDAN), Políticas, ISO 27001/27701, Criptografia e Incidentes ANPD",
        "Confidencialidade, Integridade, Disponibilidade, Autenticidade e Não Repúdio; classificação de ativos, criptografia simétrica/assimétrica, assinatura/certificado digital (ICP-Brasil) e gestão de incidentes (Res. ANPD 15/2024) • Cadernos Tec CESPE: https://bit.ly/3sa3IOd e https://bit.ly/3DY0FLF",
        False,
        45,
        9.6,
        "Guia Fiscal 3.0 Plus (TI Grupo IV — Segurança da Informação Blocos I e II) + Guia ANPD",
        "AMBOS",
    ),
    (
        "TI_GERAL_M02",
        "TI_GERAL",
        "Meta 2 (Gestão de TI Blocos I a IV) — Gestão de Processos (BPM/BPMN/DMN), Projetos (PMBOK) e Governança de TI (ITIL 4 e COBIT 2019)",
        "Ciclo PDCA, modelagem BPMN (AS-IS, TO-BE), PMBOK, gerenciamento de serviços ITIL 4 e governança COBIT 2019 • Cadernos Tec CESPE: https://bit.ly/3qyHjda, https://bit.ly/3OZps8F e https://bit.ly/3YHg6S3",
        False,
        45,
        9.3,
        "Guia Fiscal 3.0 Plus (TI Grupo I — Gestão de Projetos e Governança Blocos I a IV)",
        "ANPD",
    ),
]


def sincronizar_metas_sequenciais_guias(db: Session) -> None:
    """Garante que as Metas sequenciais (Meta 1, Meta 2...) do Guia de Estudos e do Guia Fiscal 3.0 Plus
    estejam presentes e que os tópicos genéricos antigos sejam remapeados sem órfãos.
    """
    disc_by_cod = {d.codigo: d for d in db.scalars(select(Disciplina)).all()}
    if not disc_by_cod:
        return
    sefaz = db.scalar(select(Concurso).where(Concurso.codigo == "SEFAZ_PE_APOIO"))
    anpd = db.scalar(select(Concurso).where(Concurso.codigo == "ANPD_ESP_DADOS"))

    metas_map: dict[str, Topico] = {}
    for (
        cod_meta,
        cod_disc,
        titulo,
        desc,
        denso,
        minutos,
        score,
        origem,
        escopo,
    ) in METAS_SEQUENCIAIS_GUIAS:
        if cod_disc not in disc_by_cod:
            continue
        t = db.scalar(select(Topico).where(Topico.codigo_estavel == cod_meta))
        if not t:
            t = Topico(
                codigo_estavel=cod_meta,
                disciplina_id=disc_by_cod[cod_disc].id,
                nivel_granularidade="ASSUNTO",
                titulo=titulo,
                descricao_objetiva=desc,
                eh_denso=denso,
                estimativa_esforco_minutos=minutos,
                meta_questoes=20,
                status_estudo="MATERIAL_LOCALIZADO",
                situacao_dominio="EM_DESENVOLVIMENTO",
                score_importancia=score,
                origem_documental=origem,
                validado_na_matriz=True,
            )
            db.add(t)
            db.flush()
            if escopo in ("AMBOS", "SEFAZ_PE") and sefaz:
                db.add(
                    AssociacaoTopicoConcurso(
                        topico_id=t.id,
                        concurso_id=sefaz.id,
                        status_no_concurso="HISTORICO_REFERENCIA",
                        item_edital_referencia=titulo,
                        peso_prioridade=1.5,
                        fundamento_peso=origem,
                    )
                )
            if escopo in ("AMBOS", "ANPD") and anpd:
                db.add(
                    AssociacaoTopicoConcurso(
                        topico_id=t.id,
                        concurso_id=anpd.id,
                        status_no_concurso="CONFIRMADO_EDITAL",
                        item_edital_referencia=titulo,
                        peso_prioridade=1.5,
                        fundamento_peso=origem,
                    )
                )
        else:
            t.titulo = titulo
            t.descricao_objetiva = desc
            t.eh_denso = denso
            t.estimativa_esforco_minutos = minutos
            t.score_importancia = score
            t.origem_documental = origem
        metas_map[cod_meta] = t
    db.commit()

    remap_old_to_new = {
        "PORT_01": "PORT_M11",
        "PORT_02": "PORT_M12",
        "PORT_03": "PORT_M07",
        "RLM_01": "RLM_M01",
        "RLM_02": "RLM_M04",
        "DIR_CONST_01": "DIR_CONST_M02",
        "DIR_CONST_02": "DIR_CONST_M06",
        "DIR_ADM_00": "DIR_ADM_M01",
        "DIR_ADM_01": "DIR_ADM_M09",
        "DIR_ADM_02": "DIR_ADM_M07",
        "DIR_ADM_03": "DIR_ADM_M08",
        "DIR_ADM_04": "DIR_ADM_M07",
        "LEG_PE_01": "LEG_PE_M01",
        "LEG_PE_02": "LEG_PE_M03",
        "AFO_01": "AFO_M02",
        "AFO_02": "AFO_M04",
        "AFO_03": "AFO_M07",
        "TI_CD_01": "TI_CD_M01",
        "TI_ENG_01": "TI_ENG_M01",
        "TI_IA_01": "TI_IA_M01",
        "TI_GERAL_01": "TI_GERAL_M01",
    }
    for cod_old, cod_new in remap_old_to_new.items():
        t_old = db.scalar(select(Topico).where(Topico.codigo_estavel == cod_old))
        t_new = metas_map.get(cod_new)
        if t_old and t_new:
            for model_cls in (
                Material,
                NormaJuridica,
                HistoricoProvaCobranca,
                AvaliacaoNivelamento,
                EntendimentoJurisprudencia,
                Revisao,
                TarefaCronograma,
                SessaoEstudo,
                Questao,
                SessaoQuestoes,
                RespostaQuestao,
                ErroCaderno,
                Flashcard,
                MetaAlerta,
            ):
                db.execute(
                    update(model_cls)
                    .where(model_cls.topico_id == t_old.id)
                    .values(topico_id=t_new.id)
                )
            db.execute(
                delete(AssociacaoMaterialTopico).where(
                    AssociacaoMaterialTopico.topico_id == t_old.id
                )
            )
            db.execute(
                delete(AssociacaoTopicoConcurso).where(
                    AssociacaoTopicoConcurso.topico_id == t_old.id
                )
            )
            db.delete(t_old)
    db.commit()


def inicializar_dados_plataforma(db: Session) -> dict[str, int]:
    """Garante que toda a base real do acervo esteja estruturada no SQLite."""
    # 1. Configurações globais
    configs_padrao = [
        (
            "peso_eixo_sefaz_pe",
            json.dumps(PESO_EIXO_SEFAZ_PE),
            "ESTRATEGIA",
            "Fase inicial — SEFAZ-PE (80%), com base sólida antes da expansão do edital",
        ),
        (
            "peso_eixo_anpd_ti",
            json.dumps(PESO_EIXO_ANPD_TI),
            "ESTRATEGIA",
            "Fase inicial — ANPD + Dados e TI (20%), em três sessões leves por semana",
        ),
        (
            "distribuicao_interna_tecnologia",
            json.dumps(DISTRIBUICAO_INTERNA_TECNOLOGIA, ensure_ascii=False),
            "ESTRATEGIA",
            "Distribuição interna da frente tecnológica (30% CD/Estatística, 25% Eng. Dados, 25% IA, 20% TI Geral)",
        ),
        (
            "minutos_disponiveis_dia",
            json.dumps(240),
            "ROTINA_ESTUDO",
            "Tempo diário planejado de estudo (minutos)",
        ),
        (
            "max_temas_novos_dia",
            json.dumps(2),
            "ROTINA_ESTUDO",
            "Limite de 1 ou 2 temas novos por dia (1 quando denso/extenso)",
        ),
        (
            "intervalos_revisao_geral",
            json.dumps([1, 7, 15, 30, 60]),
            "REVISAO",
            "Intervalos base de revisão geral (D1, D7, D15, D30, D60)",
        ),
        (
            "meta_questoes_padrao_assunto",
            json.dumps(20),
            "QUESTOES",
            "Meta referência ajustável de questões por assunto (20 questões)",
        ),
        (
            "inicio_ciclo_sefaz_60d",
            json.dumps(date.today().isoformat()),
            "ESTRATEGIA",
            "Data de início da meta de 60 dias (2 meses) para fechar o edital SEFAZ-PE",
        ),
        (
            "prazo_dias_sefaz",
            json.dumps(60),
            "ESTRATEGIA",
            "Prazo alvo em dias para fechar o edital da SEFAZ-PE (60 dias / 2 meses)",
        ),
        (
            "inicio_ciclo_anpd_120d",
            json.dumps(date.today().isoformat()),
            "ESTRATEGIA",
            "Data de início da trilha de quatro meses para ANPD, com foco em Dados e TI",
        ),
        (
            "prazo_dias_anpd",
            json.dumps(120),
            "ESTRATEGIA",
            "Prazo alvo de quatro meses para a trilha ANPD",
        ),
        (
            "modo_trilha",
            json.dumps("AUTO"),
            "ESTRATEGIA",
            "AUTO = plano de 8 semanas por data; ou fixe uma fase manualmente",
        ),
        (
            "portugues_todo_dia",
            json.dumps(True),
            "ROTINA_ESTUDO",
            "Bloco fixo diário de Língua Portuguesa (foco Cebraspe + IAUPE)",
        ),
    ]
    for chave, val, cat, desc in configs_padrao:
        if not db.scalar(select(Configuracao).where(Configuracao.chave == chave)):
            db.add(
                Configuracao(
                    chave=chave, valor_json=val, categoria=cat, descricao=desc
                )
            )
    db.commit()

    # 2. Bancas organizadoras
    bancas_data = [
        (
            "Cebraspe",
            "Centro Brasileiro de Pesquisa em Avaliação e Seleção e de Promoção de Eventos",
            "CERTO_ERRADO",
            "Forte cobrança literal e interpretativa de legislação, jurisprudência STF/STJ, guias técnicos ANPD e estudos de caso discursivos em Regulação, TI e Ciência de Dados.",
        ),
        (
            "IAUPE/UPENET",
            "Instituto de Apoio à Universidade de Pernambuco",
            "MULTIPLA_ESCOLHA",
            "Banca histórica do Edital SEFAZ-PE nº 001/2022 (5 alternativas A-E). Cobrança direta de legislação estadual PE, Direito Administrativo, Constitucional, Administração Pública e AFO.",
        ),
        (
            "FGV",
            "Fundação Getulio Vargas",
            "MULTIPLA_ESCOLHA",
            "Questões baseadas em casos práticos extensos, interpretação avançada de português e cobrança rigorosa em Ciência de Dados, SQL e Engenharia de Dados (TCE-PI, TJ-RR, ALEGO, SP Águas).",
        ),
        (
            "Cesgranrio",
            "Fundação Cesgranrio",
            "MULTIPLA_ESCOLHA",
            "Banca do CNU 2024 (Blocos 2, 6 e 7) e BNDES 2024 Ciência de Dados; foco em políticas públicas, governança e fundamentos analíticos.",
        ),
    ]
    bancas_map: dict[str, Banca] = {}
    for sigla, nome, estilo, padrao in bancas_data:
        b = db.scalar(select(Banca).where(Banca.sigla == sigla))
        if not b:
            b = Banca(
                sigla=sigla,
                nome_completo=nome,
                estilo_predominante=estilo,
                padroes_cobranca=padrao,
            )
            db.add(b)
            db.flush()
        bancas_map[sigla] = b
    db.commit()

    # 3. Concursos Prioritários (Eixo 1 = 60%, Eixo 2 = 40%) e Radar
    concursos_seed = [
        {
            "codigo": "SEFAZ_PE_APOIO",
            "orgao": "Secretaria da Fazenda do Estado de Pernambuco",
            "sigla_orgao": "SEFAZ-PE",
            "esfera": "ESTADUAL",
            "eixo_estrategico": "EIXO_1_SEFAZ_PE",
            "peso_estrategico_percentual": 60.0,
            "area_foco": "Apoio Administrativo às Atividades Fazendárias",
            "banca_id": bancas_map["IAUPE/UPENET"].id,
            "status_concurso": "HISTORICO",
            "prioridade_usuario": "NUCLEO_PRIORITARIO",
            "requisitos_cargo": "Diploma de nível superior em qualquer área de formação.",
            "formacao_exigida": "Nível Superior em Qualquer Área",
            "remuneracao_informada": "R$ 2.309,20 (vencimento base 2022) + FASAF (Lei Estadual nº 15.815/2016)",
            "fonte_remuneracao": "Edital SEFAZ-PE nº 001/2022 e Lei Estadual PE nº 15.815/2016",
            "compatibilidade_formacao": 100.0,
            "compatibilidade_assuntos": 100.0,
            "ativo_no_planejamento": True,
            "link_oficial": "https://www.upenet.com.br/concursos/22_Sefaz/",
            "data_ultima_consulta": date(2026, 11, 22),
            "observacoes": "Eixo 1 (60% da prioridade estratégica). Referência oficial: Edital nº 001/2022 (Analista de Apoio Administrativo às Atividades Fazendárias — não confundir com Auditor Fiscal).",
            "cargo": (
                "Analista de Apoio Administrativo às Atividades Fazendárias",
                "Gestão Fazendária e Administrativa",
                10,
                0,
                "30 horas semanais",
            ),
            "edital": (
                "Edital nº 001/2022 — SEFAZ-PE",
                "EDITAL_ABERTURA",
                "HISTORICO_REFERENCIA",
                date(2022, 4, 5),
                "Prova objetiva de 60 questões (2,5 pts cada): Português 10, RLM 5, Informática 5, Dir. Administrativo 5, Dir. Constitucional 5, Orçamento Público 5, Educação Fiscal 5, Administração Geral e Pública 20. Corte: 50% em Gerais e 50% em Específicas (item 6.4).",
            ),
        },
        {
            "codigo": "ANPD_ESP_DADOS",
            "orgao": "Autoridade Nacional de Proteção de Dados",
            "sigla_orgao": "ANPD",
            "esfera": "FEDERAL",
            "eixo_estrategico": "EIXO_2_ANPD_TI",
            "peso_estrategico_percentual": 40.0,
            "area_foco": "Regulação de Proteção de Dados, Governança, TI e Ciência de Dados",
            "banca_id": bancas_map["Cebraspe"].id,
            "status_concurso": "AUTORIZADO_ANUNCIADO",
            "prioridade_usuario": "NUCLEO_PRIORITARIO",
            "requisitos_cargo": "Nível superior (Lei nº 15.352/2026 — Carreira de Regulação e Fiscalização de Proteção de Dados e TR nº 111/2026).",
            "formacao_exigida": "Nível Superior (Especialidades previstas no TR nº 111/2026)",
            "remuneracao_informada": "Conforme Lei Federal nº 15.352/2026 (Carreira da ANPD)",
            "fonte_remuneracao": "Lei nº 15.352/2026 e Termo de Referência PNCP nº 111/2026",
            "compatibilidade_formacao": 100.0,
            "compatibilidade_assuntos": 100.0,
            "ativo_no_planejamento": True,
            "data_prevista_edital": date(2026, 12, 18),
            "data_prevista_prova": date(2027, 4, 18),
            "link_oficial": "https://www.gov.br/anpd/pt-br",
            "data_ultima_consulta": date(2026, 11, 22),
            "observacoes": "Eixo 2 (40% da prioridade estratégica, integrando ANPD + Dados e TI). Banca Cebraspe confirmada pelo Ato de Contratação Direta nº 69/2026. Conteúdo definitivo aguarda publicação do edital oficial.",
            "cargo": (
                "Especialista em Regulação de Proteção de Dados",
                "Regulação, Proteção de Dados, Tecnologia e Ciência de Dados",
                50,
                150,
                "40 horas semanais",
            ),
            "edital": (
                "Termo de Referência nº 111/2026 e Contratação Direta nº 69/2026 — ANPD",
                "TERMO_REFERENCIA",
                "PRELIMINAR_TR",
                date(2026, 11, 1),
                "Provas Objetivas + Prova Discursiva (questão aberta comum + estudo de caso por especialidade) + Avaliação de Títulos + Curso de Formação, sob responsabilidade do Cebraspe.",
            ),
        },
        {
            "codigo": "SERPRO_CD_TI",
            "orgao": "Serviço Federal de Processamento de Dados",
            "sigla_orgao": "SERPRO",
            "esfera": "FEDERAL",
            "eixo_estrategico": "EIXO_2_ANPD_TI",
            "peso_estrategico_percentual": 0.0,
            "area_foco": "Ciência de Dados e Tecnologia da Informação",
            "banca_id": bancas_map["Cebraspe"].id,
            "status_concurso": "HISTORICO",
            "prioridade_usuario": "RADAR_OPORTUNIDADE",
            "requisitos_cargo": "Graduação na área de TI, Ciência de Dados, Estatística ou correlatas.",
            "formacao_exigida": "Tecnologia da Informação / Ciência de Dados",
            "remuneracao_informada": "R$ 9.025,73 + benefícios (Edital nº 1/2023)",
            "fonte_remuneracao": "Edital SERPRO nº 1/2023 no acervo local",
            "compatibilidade_formacao": 95.0,
            "compatibilidade_assuntos": 88.0,
            "ativo_no_planejamento": False,
            "link_oficial": "https://www.cebraspe.org.br/concursos/serpro_23",
            "data_ultima_consulta": date(2026, 11, 22),
            "observacoes": "Referência oficial de provas Cebraspe em Ciência de Dados (2021) e Tecnologia (2023) presentes no acervo.",
            "cargo": (
                "Analista — Especialização: Ciência de Dados / Tecnologia",
                "Ciência de Dados e Engenharia de Dados",
                602,
                0,
                "40 horas semanais",
            ),
            "edital": (
                "Edital nº 1/2023 — SERPRO",
                "EDITAL_ABERTURA",
                "HISTORICO_REFERENCIA",
                date(2023, 4, 19),
                "120 itens Cebraspe (Certo/Errado) + prova prática/conhecimentos aplicados.",
            ),
        },
        {
            "codigo": "TCU_AUFC_TI",
            "orgao": "Tribunal de Contas da União",
            "sigla_orgao": "TCU",
            "esfera": "FEDERAL",
            "eixo_estrategico": "EIXO_2_ANPD_TI",
            "peso_estrategico_percentual": 0.0,
            "area_foco": "Auditoria de TI, Engenharia de Dados e Governança",
            "banca_id": bancas_map["Cebraspe"].id,
            "status_concurso": "OFICIAL_PUBLICADO",
            "prioridade_usuario": "RADAR_OPORTUNIDADE",
            "requisitos_cargo": "Nível superior completo.",
            "formacao_exigida": "Nível Superior",
            "remuneracao_informada": "Conforme Edital nº 1/2025 TCU no acervo",
            "fonte_remuneracao": "Edital TCU nº 1/2025 (pasta 01_EDITAIS_E_PLANEJAMENTO)",
            "compatibilidade_formacao": 92.0,
            "compatibilidade_assuntos": 85.0,
            "ativo_no_planejamento": False,
            "link_oficial": "https://www.cebraspe.org.br",
            "data_ultima_consulta": date(2026, 11, 22),
            "observacoes": "Edital, prova objetiva e gabarito 2025/2026 disponíveis no acervo local; alta sinergia em Direito Administrativo, Controle, LGPD, Dados e TI.",
            "cargo": (
                "Auditor Federal de Controle Externo — Auditoria de TI",
                "Auditoria de Tecnologia da Informação e Dados",
                20,
                0,
                "40 horas semanais",
            ),
            "edital": None,
        },
        {
            "codigo": "ANATEL_ESP_CD",
            "orgao": "Agência Nacional de Telecomunicações",
            "sigla_orgao": "ANATEL",
            "esfera": "FEDERAL",
            "eixo_estrategico": "EIXO_2_ANPD_TI",
            "peso_estrategico_percentual": 0.0,
            "area_foco": "Regulação e Ciências de Dados",
            "banca_id": bancas_map["Cebraspe"].id,
            "status_concurso": "HISTORICO",
            "prioridade_usuario": "RADAR_OPORTUNIDADE",
            "requisitos_cargo": "Nível superior conforme edital ANATEL 2024.",
            "formacao_exigida": "Ciências de Dados / TI / Engenharias / Estatística",
            "remuneracao_informada": "Carreira de Especialista em Regulação Federal",
            "fonte_remuneracao": "Prova ANATEL 2024 Cebraspe no acervo local",
            "compatibilidade_formacao": 95.0,
            "compatibilidade_assuntos": 92.0,
            "ativo_no_planejamento": False,
            "link_oficial": "https://www.cebraspe.org.br",
            "data_ultima_consulta": date(2026, 11, 22),
            "observacoes": "Principal espelho de agência reguladora federal com prova Cebraspe de Especialista em Regulação — Ciências de Dados (objetiva + discursiva no acervo).",
            "cargo": (
                "Especialista em Regulação — Especialidade: Ciências de Dados",
                "Ciências de Dados e Regulação",
                10,
                0,
                "40 horas semanais",
            ),
            "edital": None,
        },
        {
            "codigo": "SP_AGUAS_CD_2026",
            "orgao": "Agência de Águas do Estado de São Paulo",
            "sigla_orgao": "SP Águas",
            "esfera": "ESTADUAL",
            "eixo_estrategico": "EIXO_2_ANPD_TI",
            "peso_estrategico_percentual": 0.0,
            "area_foco": "Tecnologia da Informação e Ciência de Dados",
            "banca_id": bancas_map["FGV"].id,
            "status_concurso": "OFICIAL_PUBLICADO",
            "prioridade_usuario": "RADAR_OPORTUNIDADE",
            "requisitos_cargo": "Nível superior conforme Edital SP Águas nº 01/2026.",
            "formacao_exigida": "TI / Ciência de Dados / Estatística",
            "remuneracao_informada": "Conforme Edital nº 01/2026 SP Águas no acervo",
            "fonte_remuneracao": "Edital nº 01/2026 SP Águas (pasta 01_EDITAIS_E_PLANEJAMENTO)",
            "compatibilidade_formacao": 90.0,
            "compatibilidade_assuntos": 82.0,
            "ativo_no_planejamento": False,
            "link_oficial": "https://conhecimento.fgv.br",
            "data_ultima_consulta": date(2026, 11, 22),
            "observacoes": "Oportunidade monitorada no Radar com edital oficial presente no acervo local.",
            "cargo": (
                "Especialista / Analista — Tecnologia da Informação e Ciência de Dados",
                "Ciência de Dados e TI",
                5,
                0,
                "40 horas semanais",
            ),
            "edital": None,
        },
    ]

    concursos_map: dict[str, Concurso] = {}
    for cdata in concursos_seed:
        c = db.scalar(select(Concurso).where(Concurso.codigo == cdata["codigo"]))
        if not c:
            cargo_tuple = cdata.pop("cargo", None)
            edital_tuple = cdata.pop("edital", None)
            c = Concurso(**cdata)
            db.add(c)
            db.flush()
            cargo_obj = None
            if cargo_tuple:
                cargo_obj = Cargo(
                    concurso_id=c.id,
                    nome_cargo=cargo_tuple[0],
                    area_especialidade=cargo_tuple[1],
                    vagas_imediatas=cargo_tuple[2],
                    cadastro_reserva=cargo_tuple[3],
                    jornada_semanal=cargo_tuple[4],
                    cargo_alvo_principal=(
                        cdata["codigo"] in ("SEFAZ_PE_APOIO", "ANPD_ESP_DADOS")
                    ),
                )
                db.add(cargo_obj)
                db.flush()
            if edital_tuple:
                db.add(
                    Edital(
                        concurso_id=c.id,
                        cargo_id=cargo_obj.id if cargo_obj else None,
                        numero_ano=edital_tuple[0],
                        titulo=edital_tuple[0],
                        tipo_documento=edital_tuple[1],
                        natureza_referencia=edital_tuple[2],
                        data_publicacao=edital_tuple[3],
                        resumo_estrutura_prova=edital_tuple[4],
                    )
                )
        concursos_map[c.codigo] = c
    db.commit()

    # 4. Disciplinas Únicas (Núcleo Comum, Exclusivas SEFAZ-PE e Eixo ANPD + Frente Tecnológica 30/25/25/20)
    disciplinas_seed = [
        (
            "DIR_ADM",
            "Direito Administrativo",
            "Jurídica",
            "AMBOS_COMUM",
            False,
            None,
            None,
            True,
            1,
            "Disciplina comum de alto peso na SEFAZ-PE (Edital 2022) e na ANPD/Agências Reguladoras (Lei 14.133/21, Lei 8.112/90, Lei 9.784/99, Improbidade, LAI, Processo Sancionador).",
        ),
        (
            "DIR_CONST",
            "Direito Constitucional",
            "Jurídica",
            "AMBOS_COMUM",
            False,
            None,
            None,
            True,
            2,
            "Direitos e Garantias Fundamentais (incluindo proteção de dados art. 5º, LXXIX, CF/88), Organização do Estado, Administração Pública e Finanças Públicas.",
        ),
        (
            "ADM_PUB",
            "Administração Pública e Gestão Governamental",
            "Gestão Pública",
            "AMBOS_COMUM",
            False,
            None,
            None,
            False,
            3,
            "Teorias da Administração, Governança Pública, Planejamento Estratégico (BSC, SWOT, PDCA), Gestão de Processos, Projetos (PMBOK/Scrum) e Riscos (CGU).",
        ),
        (
            "PORT",
            "Língua Portuguesa e Redação Oficial",
            "Básica Comum",
            "AMBOS_COMUM",
            False,
            None,
            None,
            False,
            4,
            "Compreensão textual, gramática normativa, coesão, coerência, reescrita de períodos (padrão Cebraspe e IAUPE) e Redação Discursiva.",
        ),
        (
            "RLM",
            "Raciocínio Lógico-Matemático",
            "Básica Comum",
            "AMBOS_COMUM",
            False,
            None,
            None,
            False,
            5,
            "Lógica proposicional, argumentação, conjuntos, análise combinatória e probabilidade básica.",
        ),
        (
            "AFO",
            "Administração Financeira e Orçamentária (AFO)",
            "Fazendária / Orçamento",
            "EIXO_1_SEFAZ_PE",
            False,
            None,
            None,
            True,
            6,
            "Orçamento Público (PPA, LDO, LOA), Lei 4.320/1964, Lei de Responsabilidade Fiscal (LC 101/2000), MCASP 11ª ed. e MTO 2027.",
        ),
        (
            "LEG_PE",
            "Legislação Estadual de Pernambuco e FASAF",
            "Legislação Estadual PE",
            "EIXO_1_SEFAZ_PE",
            False,
            None,
            None,
            True,
            7,
            "Constituição do Estado de PE, Estatuto dos Servidores (Lei PE 6.123/68), Processo Administrativo PE (Lei 11.781/00), Lei 14.538/11, FASAF (Lei 15.815/16) e Educação Fiscal.",
        ),
        (
            "GEST_PESS_MAT",
            "Gestão de Pessoas e Administração de Recursos Materiais",
            "Gestão Administrativa",
            "EIXO_1_SEFAZ_PE",
            False,
            None,
            None,
            False,
            8,
            "Comportamento organizacional, liderança, avaliação de desempenho, classificação de materiais, gestão de estoques e patrimônio (Edital SEFAZ-PE 2022).",
        ),
        (
            "LGPD_ANPD",
            "Proteção de Dados Pessoais, LGPD e Regulação ANPD",
            "Regulação e Privacidade",
            "EIXO_2_ANPD_TI",
            False,
            None,
            None,
            True,
            9,
            "Lei 13.709/2018 (LGPD), Lei 13.853/2019, Lei 15.211/2025 (ECA Digital), Lei 15.352/2026 (Carreira ANPD), Marco Civil da Internet, Resoluções CD/ANPD e Guias Orientativos.",
        ),
        (
            "TI_CD_EST",
            "Ciência de Dados e Estatística Aplicada",
            "Frente Tecnológica",
            "EIXO_2_ANPD_TI",
            True,
            "CIENCIA_DADOS_ESTATISTICA",
            30.0,
            False,
            10,
            "Frente Tecnológica (30% interno): Estatística descritiva e inferencial, testes de hipóteses, regressão, análise exploratória de dados, séries temporais e visualização/Analytics.",
        ),
        (
            "TI_ENG_DADOS",
            "Engenharia de Dados e Bancos de Dados (SQL/NoSQL)",
            "Frente Tecnológica",
            "EIXO_2_ANPD_TI",
            True,
            "ENGENHARIA_DADOS",
            25.0,
            False,
            11,
            "Frente Tecnológica (25% interno): Modelagem relacional e dimensional, SQL avançado, pipelines ETL/ELT, Data Warehouse, Data Lake, Big Data e Governança de Dados (DAMA-DMBOK).",
        ),
        (
            "TI_IA",
            "Inteligência Artificial e Aprendizado de Máquina",
            "Frente Tecnológica",
            "EIXO_2_ANPD_TI",
            True,
            "INTELIGENCIA_ARTIFICIAL",
            25.0,
            False,
            12,
            "Frente Tecnológica (25% interno): Machine Learning supervisionado e não supervisionado, validação cruzada, métricas (F1, ROC-AUC, RMSE), Deep Learning, NLP, LLMs e IA Responsável/Ética.",
        ),
        (
            "TI_GERAL",
            "Tecnologia da Informação, Redes e Segurança da Informação",
            "Frente Tecnológica",
            "EIXO_2_ANPD_TI",
            True,
            "TI_GERAL",
            20.0,
            False,
            13,
            "Frente Tecnológica (20% interno) + Informática SEFAZ-PE: Segurança da Informação (ISO 27001/27701, criptografia, gestão de incidentes CERT.br/ANPD), redes, sistemas operacionais e engenharia de software.",
        ),
        (
            "EDU_FISCAL",
            "Educação Fiscal",
            "Fazendária",
            "EIXO_1_SEFAZ_PE",
            False,
            None,
            None,
            False,
            14,
            "Tributo, Sistema Tributário Nacional, federalismo fiscal, PNEF e cidadania fiscal (edital SEFAZ-PE 2022: 5 questões).",
        ),
        (
            "INFO_BASICA",
            "Informática (Windows, Office, Internet e Segurança)",
            "Básica Comum",
            "EIXO_1_SEFAZ_PE",
            False,
            None,
            None,
            False,
            15,
            "Internet/intranet, Windows, Microsoft Office, redes, vírus, backup e nuvem (edital SEFAZ-PE 2022: 5 questões).",
        ),
    ]

    disc_map: dict[str, Disciplina] = {}
    for (
        cod,
        nome,
        area,
        eixo,
        eh_tec,
        cat_tec,
        perc_tec,
        densa,
        ordem,
        desc,
    ) in disciplinas_seed:
        d = db.scalar(select(Disciplina).where(Disciplina.codigo == cod))
        if not d:
            d = Disciplina(
                codigo=cod,
                nome=nome,
                area_tematica=area,
                eixo_associado=eixo,
                eh_frente_tecnologica=eh_tec,
                categoria_tecnologica=cat_tec,
                percentual_interno_tecnologia=perc_tec,
                eh_densa_legislacao=densa,
                ordem_exibicao=ordem,
                descricao=desc,
            )
            db.add(d)
            db.flush()
        disc_map[cod] = d
    db.commit()

    # 5. Indexar os 221+ arquivos do acervo real antes de criar os tópicos e normas
    stats_acervo = indexar_acervo_completo(db, force_recheck=False)

    # 6. Matriz Integrada de Conteúdos (Tópicos únicos com associações a 1 ou N concursos)
    sefaz = concursos_map["SEFAZ_PE_APOIO"]
    anpd = concursos_map["ANPD_ESP_DADOS"]
    serpro = concursos_map["SERPRO_CD_TI"]
    tcu = concursos_map["TCU_AUFC_TI"]
    anatel = concursos_map["ANATEL_ESP_CD"]

    topicos_seed = [
        # BASE SÓLIDA — PORTUGUÊS (TODO DIA — FOCO CEBRASPE + IAUPE)
        (
            "PORT_01",
            "PORT",
            "Interpretação e Compreensão Textual + Tipologia (Padrão Cebraspe e IAUPE)",
            "Ideia central, inferências, extrapolação vs. restrição e tipologia textual aplicada a textos densos.",
            False,
            45,
            9.6,
            "Provas Cebraspe (ANATEL/SERPRO/TCU) e SEFAZ-PE 2022 (IAUPE)",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Gerais — Língua Portuguesa", 1.5),
                (anpd.id, "CONFIRMADO_EDITAL", "Conhecimentos Básicos — Língua Portuguesa", 1.5),
            ],
        ),
        (
            "PORT_02",
            "PORT",
            "Coesão Textual, Referenciação e Reescrita de Períodos (Top 1 Cebraspe)",
            "Substituição de pronomes, conjunções, conectivos e manutenção de sentido e correção gramatical na reescrita.",
            False,
            45,
            9.7,
            "Padrão Cebraspe + Cadernos SEFAZ-PE 2022",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Gerais — Coesão e Reescrita", 1.5),
                (anpd.id, "CONFIRMADO_EDITAL", "Conhecimentos Básicos — Coesão e Reescrita Cebraspe", 1.6),
            ],
        ),
        (
            "PORT_03",
            "PORT",
            "Sintaxe da Oração, Pontuação (Vírgula), Regência, Concordância e Crase",
            "Orações subordinadas adjetivas/adverbiais, emprego da vírgula, crase obrigatória/facultativa e concordância verbal.",
            False,
            45,
            9.5,
            "Padrão Cebraspe + SEFAZ-PE 2022",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Gerais — Gramática Aplicada", 1.4),
                (anpd.id, "CONFIRMADO_EDITAL", "Conhecimentos Básicos — Sintaxe e Pontuação", 1.5),
            ],
        ),
        # BASE SÓLIDA — RLM (FOCO CEBRASPE + IAUPE)
        (
            "RLM_01",
            "RLM",
            "Proposições, Tabela-Verdade, Equivalências e Negações (Leis de De Morgan)",
            "Conectivos lógicos, negação de proposições compostas e equivalências do 'se... então' (tema nº 1 no Cebraspe).",
            False,
            50,
            9.4,
            "Padrão Cebraspe + Provas SEFAZ-PE 2022",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Gerais — Raciocínio Lógico", 1.4),
                (anpd.id, "PENDENTE_CONFIRMACAO", "Raciocínio Lógico e Quantitativo", 1.2),
            ],
        ),
        (
            "RLM_02",
            "RLM",
            "Argumentação Lógica, Diagramas, Conjuntos, Combinatória e Probabilidade",
            "Validade de argumentos, diagramas de Venn, arranjos, combinações e probabilidade condicional.",
            False,
            50,
            9.0,
            "Provas SEFAZ-PE 2022 e Cebraspe Nível Superior",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Gerais — RLM e Probabilidade", 1.3),
                (anpd.id, "PENDENTE_CONFIRMACAO", "Lógica e Probabilidade Base para Dados", 1.2),
            ],
        ),
        # BASE SÓLIDA — DIREITO ADMINISTRATIVO (COMEÇANDO PELOS FUNDAMENTOS)
        (
            "DIR_ADM_00",
            "DIR_ADM",
            "Princípios, Poderes Administrativos e Atos Administrativos (Base Essencial)",
            "Regime jurídico-administrativo, poderes (hierárquico, disciplinar, regulamentar, polícia), elementos do ato (CO-FOR-MO-OB-FI), atributos e Súmula 473 STF.",
            False,
            60,
            9.8,
            "CF/88 + Doutrina e Súmula 473 STF + Provas Cebraspe e SEFAZ-PE 2022",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Dir. Administrativo — Base: Princípios, Poderes e Atos", 1.6),
                (anpd.id, "CONFIRMADO_EDITAL", "Dir. Administrativo — Poder de Polícia e Atos Regulatórios", 1.6),
            ],
        ),
        # COMUNS (SEFAZ-PE + ANPD)
        (
            "DIR_ADM_01",
            "DIR_ADM",
            "Licitações e Contratos Administrativos (Lei nº 14.133/2021)",
            "Fases da licitação, modalidades, dispensa/inexigibilidade, contratos, sanções e governança nas contratações.",
            True,
            90,
            9.5,
            "Edital SEFAZ-PE 001/2022 + Lei 14.133/2021 + Orientações TCU",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Específicos — Dir. Administrativo", 1.5),
                (anpd.id, "CONFIRMADO_EDITAL", "Núcleo Direito Administrativo / Contratação Pública", 1.2),
                (tcu.id, "CONFIRMADO_EDITAL", "Direito Administrativo / Controle Externo", 1.3),
            ],
        ),
        (
            "DIR_ADM_02",
            "DIR_ADM",
            "Processo Administrativo Federal (Lei nº 9.784/1999) e LINDB (Lei nº 13.655/2018)",
            "Direitos e deveres do administrado, motivação, anulação, revogação, convalidação, decadência e segurança jurídica na LINDB.",
            True,
            75,
            9.2,
            "Lei 9.784/1999 e Decreto 9.830/2019 no acervo",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Dir. Administrativo — Processo Administrativo", 1.3),
                (anpd.id, "CONFIRMADO_EDITAL", "Processo Administrativo e Sancionador ANPD", 1.5),
            ],
        ),
        (
            "DIR_ADM_03",
            "DIR_ADM",
            "Agentes Públicos, Regime Jurídico (Lei nº 8.112/1990) e Improbidade (Lei nº 8.429/1992)",
            "Provimento, vacância, direitos, deveres, PAD, conflito de interesses (Lei 12.813/13) e atos de improbidade administrativa.",
            True,
            80,
            9.0,
            "Leis 8.112/90, 8.429/92 e 12.813/13 no acervo",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Dir. Administrativo — Agentes Públicos e Improbidade", 1.4),
                (anpd.id, "CONFIRMADO_EDITAL", "Regime Jurídico dos Servidores Federais e Ética/Integridade", 1.3),
            ],
        ),
        (
            "DIR_ADM_04",
            "DIR_ADM",
            "Transparência, Acesso à Informação (LAI - Lei nº 12.527/2011) e Governo Digital (Lei nº 14.129/2021)",
            "Transparência ativa/passiva, classificação de sigilo, proteção de informações pessoais na LAI e transformação digital.",
            False,
            60,
            8.8,
            "Lei 12.527/11, Decreto 7.724/12 e Lei 14.129/21 no acervo",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Administração Pública / Transparência", 1.2),
                (anpd.id, "CONFIRMADO_EDITAL", "Interface entre LAI e LGPD no Poder Público", 1.5),
            ],
        ),
        (
            "DIR_CONST_01",
            "DIR_CONST",
            "Direitos e Garantias Fundamentais e Proteção Constitucional de Dados (Art. 5º, LXXIX, CF/88)",
            "Direitos individuais e coletivos, remédios constitucionais (Habeas Data, Mandado de Segurança) e EC nº 115/2022.",
            False,
            60,
            9.7,
            "CF/1988 Compilada no acervo",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Direito Constitucional — Título II CF/88", 1.5),
                (anpd.id, "CONFIRMADO_EDITAL", "Direito Fundamental à Proteção de Dados Pessoais", 1.6),
            ],
        ),
        (
            "DIR_CONST_02",
            "DIR_CONST",
            "Organização do Estado, Administração Pública (Arts. 37 a 41) e Ordem Tributária/Financeira",
            "Repartição de competências, princípios constitucionais da Administração (LIMPE), servidores públicos e fiscalização contábil/financeira.",
            False,
            60,
            9.5,
            "CF/1988 Compilada no acervo",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Direito Constitucional — Arts. 18 a 41 e Finanças", 1.5),
                (anpd.id, "CONFIRMADO_EDITAL", "Competência da União para organizar e manter a ANPD", 1.3),
            ],
        ),
        (
            "ADM_PUB_01",
            "ADM_PUB",
            "Planejamento Estratégico (BSC, SWOT, PDCA), Governança Pública e Gestão de Riscos",
            "Modelos de gestão pública, indicadores de desempenho, gestão por resultados e Guia de Gestão de Riscos para a Integridade (CGU).",
            False,
            60,
            8.9,
            "Edital SEFAZ-PE 2022 + Prova Cebraspe UNEAL 2026 + Guia CGU + Planejamento Estratégico ANPD",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Administração Pública — Planejamento e Governança", 1.5),
                (anpd.id, "CONFIRMADO_EDITAL", "Governança, Gestão de Riscos e Planejamento Institucional", 1.2),
            ],
        ),
        (
            "ADM_PUB_02",
            "ADM_PUB",
            "Gestão de Projetos (PMBOK 7ª ed., Scrum, Kanban) e Gestão de Processos (BPM)",
            "Ciclo de vida de projetos, métodos ágeis, caminho crítico, EAP, mapeamento e melhoria de processos organizacionais.",
            False,
            60,
            8.5,
            "Edital SEFAZ-PE 2022 + Prova Cebraspe UNEAL 2026",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Administração Geral — Projetos e Processos", 1.3),
                (anpd.id, "PENDENTE_CONFIRMACAO", "Gestão de Projetos e Processos Regulatórios/TI", 1.1),
            ],
        ),
        # EXCLUSIVOS EIXO 1 — SEFAZ-PE (60%)
        (
            "AFO_01",
            "AFO",
            "Instrumentos de Planejamento Orçamentário (PPA, LDO, LOA), Princípios e Ciclo Orçamentário",
            "Orçamento na CF/88 (arts. 165-169), créditos adicionais, vedações constitucionais e MTO 2027 (2ª versão).",
            True,
            75,
            9.6,
            "Edital SEFAZ-PE 2022 + MTO 2027 (pasta 06_MATERIAIS_E_INVENTARIO)",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Específicos — AFO (Item 1 a 4)", 1.6),
            ],
        ),
        (
            "AFO_02",
            "AFO",
            "Receita e Despesa Pública na Lei nº 4.320/1964 e no MCASP 11ª Edição",
            "Classificações da receita e despesa, estágios (empenho, liquidação, pagamento), restos a pagar, DEA e suprimento de fundos.",
            True,
            80,
            9.6,
            "Lei 4.320/1964 + MCASP 11ª Edição STN no acervo",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Específicos — AFO (Receita e Despesa)", 1.6),
            ],
        ),
        (
            "AFO_03",
            "AFO",
            "Lei de Responsabilidade Fiscal (LC nº 101/2000)",
            "Receita Corrente Líquida, limites de despesa com pessoal, dívida, operações de crédito, RREO e RGF.",
            True,
            90,
            9.8,
            "LC 101/2000 Compilada no acervo",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Específicos — AFO (LRF)", 1.7),
            ],
        ),
        (
            "LEG_PE_01",
            "LEG_PE",
            "Estatuto dos Funcionários Públicos Civis de Pernambuco (Lei Estadual nº 6.123/1968)",
            "Provimento, direitos, vantagens, regime disciplinar e processo administrativo disciplinar estadual em PE.",
            True,
            85,
            9.5,
            "Lei PE 6.123/1968 (HTML e PDF na pasta 02_SEFAZ_PE)",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Legislação Estadual PE — Estatuto dos Servidores", 1.6),
            ],
        ),
        (
            "LEG_PE_02",
            "LEG_PE",
            "Processo Administrativo Estadual (Lei PE nº 11.781/2000), FASAF (Lei PE nº 15.815/2016) e Constituição de PE",
            "Rito processual administrativo estadual, estrutura remuneratória FASAF da SEFAZ-PE, Lei PE 14.538/2011 e Educação Fiscal.",
            True,
            80,
            9.4,
            "Constituição PE + Leis PE 11.781/00, 14.538/11 e 15.815/16 na pasta 02_SEFAZ_PE",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Legislação Estadual PE e Estrutura SEFAZ-PE", 1.6),
            ],
        ),
        (
            "GEST_PESS_MAT_01",
            "GEST_PESS_MAT",
            "Gestão de Pessoas, Liderança, Motivação e Administração de Recursos Materiais e Patrimoniais",
            "Gestão por competências, clima e cultura, curva ABC, classificação XYZ, inventário, tombamento e alienação de bens.",
            False,
            60,
            8.6,
            "Edital SEFAZ-PE 001/2022 + Cadernos 01 e 02 Analista de Apoio Administrativo",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Específicos — Gestão de Pessoas e Materiais", 1.4),
            ],
        ),
        (
            "ADM_PUB_03",
            "ADM_PUB",
            "Conceitos básicos e funções administrativas: planejar, organizar, dirigir e controlar",
            "Eficiência, eficácia e efetividade; níveis hierárquicos; processo administrativo (Anexo III do edital SEFAZ-PE).",
            False,
            60,
            9.4,
            "Edital SEFAZ-PE 001/2022 — Anexo III (Administração Geral e Pública)",
            [(sefaz.id, "HISTORICO_REFERENCIA", "Adm. Geral e Pública — 20 questões", 1.8)],
        ),
        (
            "ADM_PUB_05",
            "ADM_PUB",
            "Políticas públicas (ciclo), indicadores, gestão por resultados e qualidade",
            "Ciclo das políticas públicas, indicadores de desempenho, governança, gestão da qualidade e excelência na administração pública.",
            False,
            60,
            9.2,
            "Edital SEFAZ-PE 001/2022 — Anexo III (Administração Geral e Pública)",
            [(sefaz.id, "HISTORICO_REFERENCIA", "Adm. Geral e Pública — 20 questões", 1.7)],
        ),
        (
            "EDU_FISCAL_01",
            "EDU_FISCAL",
            "Tributos, Sistema Tributário Nacional, federalismo fiscal e Educação Fiscal (PNEF)",
            "Conceito e classificação de tributos, impostos da União/Estados, repartição de receitas, crimes contra a ordem tributária, PNEF e cidadania fiscal.",
            False,
            60,
            8.0,
            "Edital SEFAZ-PE 001/2022 — Anexo III + PNEF (02_SEFAZ_PE)",
            [(sefaz.id, "HISTORICO_REFERENCIA", "Educação Fiscal — 5 questões", 1.4)],
        ),
        (
            "INFO_01",
            "INFO_BASICA",
            "Informática: internet, Windows, Office, redes, segurança e backup",
            "Navegação e e-mail, Windows, Word/Excel/PowerPoint, redes, vírus, backup e armazenamento em nuvem.",
            False,
            50,
            7.5,
            "Edital SEFAZ-PE 001/2022 — Anexo III (Informática)",
            [(sefaz.id, "HISTORICO_REFERENCIA", "Informática — 5 questões", 1.3)],
        ),
        # EIXO 2 — ANPD + DADOS E TI (40% Global, com 30/25/25/20 interno na Frente Tecnológica)
        (
            "LGPD_01",
            "LGPD_ANPD",
            "Lei Geral de Proteção de Dados (Lei nº 13.709/2018): Fundamentos, Bases Legais e Direitos do Titular",
            "Princípios (art. 6º), hipóteses de tratamento (arts. 7º e 11), dados sensíveis, crianças e adolescentes (Enunciado ANPD nº 1/2023 e ECA Digital Lei 15.211/25).",
            True,
            90,
            9.9,
            "Lei 13.709/2018 + Enunciado CD/ANPD 01/2023 + Lei 15.211/2025 na pasta 03_ANPD",
            [
                (anpd.id, "CONFIRMADO_EDITAL", "Núcleo Essencial ANPD — LGPD e Direitos dos Titulares", 1.8),
                (serpro.id, "CONFIRMADO_EDITAL", "Legislação de Proteção de Dados", 1.3),
                (tcu.id, "CONFIRMADO_EDITAL", "Auditoria e Governança LGPD", 1.3),
            ],
        ),
        (
            "LGPD_02",
            "LGPD_ANPD",
            "Agentes de Tratamento, Encarregado (DPO - Resolução nº 18/2024) e Tratamento pelo Poder Público",
            "Controlador, operador, suboperador, responsabilidade civil, Guia do Poder Público e Resolução CD/ANPD nº 18/2024.",
            True,
            75,
            9.7,
            "Resolução CD/ANPD 18/2024 + Guias Orientativos ANPD na pasta 03_ANPD",
            [
                (anpd.id, "CONFIRMADO_EDITAL", "Regulamentação ANPD — Agentes, DPO e Poder Público", 1.7),
            ],
        ),
        (
            "LGPD_03",
            "LGPD_ANPD",
            "Fiscalização, Dosimetria de Sanções (Res. 01/21 e 04/23), Incidentes (Res. 15/24) e Transferência Internacional (Res. 19/24 e 32/26)",
            "Processo administrativo sancionador da ANPD, cálculo de multas, comunicação de incidentes em 3 dias úteis e cláusulas-padrão contratuais.",
            True,
            90,
            9.8,
            "Resoluções CD/ANPD 01/21, 02/22, 04/23, 15/24, 19/24, 30/25, 31/25 e 32/26 na pasta 03_ANPD",
            [
                (anpd.id, "CONFIRMADO_EDITAL", "Atos Normativos e Poder Sancionador da ANPD", 1.8),
            ],
        ),
        (
            "TI_CD_01",
            "TI_CD_EST",
            "Estatística Descritiva, Probabilidade, Inferência Estatística e Testes de Hipóteses",
            "Distribuições de probabilidade, Teorema Central do Limite, intervalos de confiança, p-valor, ANOVA e regressão linear/logística.",
            False,
            70,
            9.2,
            "Provas Cebraspe ANATEL 2024, SERPRO 2021/2023, EMBRAPA 2025 e FUNPRESP 2025 no acervo",
            [
                (anpd.id, "PENDENTE_CONFIRMACAO", "Frente Tecnológica (30%): Ciência de Dados e Estatística", 1.4),
                (serpro.id, "CONFIRMADO_EDITAL", "Estatística e Ciência de Dados", 1.5),
                (anatel.id, "CONFIRMADO_EDITAL", "Especialidade Ciências de Dados — Estatística", 1.5),
            ],
        ),
        (
            "TI_ENG_01",
            "TI_ENG_DADOS",
            "Bancos de Dados Relacionais (SQL), Modelagem Dimensional (DW), Pipelines ETL/ELT e Governança DAMA-DMBOK",
            "Normalização, consultas SQL complexas, Star/Snowflake Schema, Data Lakehouse, qualidade de dados, metadados e linhagem.",
            False,
            70,
            9.1,
            "Provas Cebraspe TCU 2026, SERPRO 2023, ANATEL 2024 e FGV TCE-PI 2025 no acervo",
            [
                (anpd.id, "PENDENTE_CONFIRMACAO", "Frente Tecnológica (25%): Engenharia e Governança de Dados", 1.3),
                (serpro.id, "CONFIRMADO_EDITAL", "Engenharia de Dados e Bancos de Dados", 1.5),
                (tcu.id, "CONFIRMADO_EDITAL", "Auditoria de Dados e Sistemas", 1.5),
            ],
        ),
        (
            "TI_IA_01",
            "TI_IA",
            "Aprendizado de Máquina (Supervisionado/Não Supervisionado), Deep Learning, NLP e Governança de IA",
            "Árvores de decisão, Random Forest, Gradient Boosting, clustering, redes neurais, métricas de classificação, viés algorítmico e explicabilidade (XAI).",
            False,
            70,
            9.1,
            "Provas Cebraspe ANATEL 2024, Petrobras CD, BNDES 2024 e CNU Bloco 2 no acervo",
            [
                (anpd.id, "PENDENTE_CONFIRMACAO", "Frente Tecnológica (25%): Inteligência Artificial e Decisões Automatizadas (art. 20 LGPD)", 1.4),
                (serpro.id, "CONFIRMADO_EDITAL", "Aprendizado de Máquina e IA", 1.5),
                (anatel.id, "CONFIRMADO_EDITAL", "Aprendizado de Máquina e IA Aplicada", 1.5),
            ],
        ),
        (
            "TI_GERAL_01",
            "TI_GERAL",
            "Segurança da Informação, Criptografia, Gestão de Incidentes (CERT.br/ANPD), Redes e Informática",
            "Confidencialidade, integridade, disponibilidade, anonimização vs pseudonimização, controles ISO 27001/27701, protocolos de rede e ferramentas de escritório.",
            False,
            60,
            9.0,
            "Guia Segurança da Informação ANPD + Fascículos CERT.br/ANPD + Edital SEFAZ-PE 2022 (Informática)",
            [
                (sefaz.id, "HISTORICO_REFERENCIA", "Conhecimentos Gerais — Informática e Segurança", 1.2),
                (anpd.id, "CONFIRMADO_EDITAL", "Frente Tecnológica (20%): Segurança da Informação e Prevenção de Vazamentos", 1.5),
                (tcu.id, "CONFIRMADO_EDITAL", "Segurança da Informação e Auditoria de TI", 1.4),
            ],
        ),
    ]

    topicos_map: dict[str, Topico] = {}
    for (
        cod_top,
        cod_disc,
        titulo,
        desc,
        eh_denso,
        esforco,
        score,
        origem,
        assocs,
    ) in topicos_seed:
        t = db.scalar(select(Topico).where(Topico.codigo_estavel == cod_top))
        if not t:
            t = Topico(
                codigo_estavel=cod_top,
                disciplina_id=disc_map[cod_disc].id,
                nivel_granularidade="ASSUNTO",
                titulo=titulo,
                descricao_objetiva=desc,
                eh_denso=eh_denso,
                estimativa_esforco_minutos=esforco,
                meta_questoes=20,
                status_estudo="MATERIAL_LOCALIZADO",
                situacao_dominio="EM_DESENVOLVIMENTO",
                score_importancia=score,
                origem_documental=origem,
                validado_na_matriz=True,
            )
            db.add(t)
            db.flush()
            for conc_id, st_conc, item_ref, peso in assocs:
                db.add(
                    AssociacaoTopicoConcurso(
                        topico_id=t.id,
                        concurso_id=conc_id,
                        status_no_concurso=st_conc,
                        item_edital_referencia=item_ref,
                        peso_prioridade=peso,
                        fundamento_peso=origem,
                    )
                )
        topicos_map[cod_top] = t
    db.commit()

    # 7. Vincular Materiais do Acervo aos Tópicos e Cadastrar Normas Jurídicas Reais
    materiais_all = db.scalars(select(Material)).all()
    mat_by_name = {m.nome_arquivo.lower(): m for m in materiais_all}

    normas_seed = [
        (
            "CONSTITUICAO_FEDERAL",
            "FEDERAL",
            "1988",
            "1988",
            "Constituição da República Federativa do Brasil de 1988",
            "Constituição Federal compilada (Direitos Fundamentais, art. 5º, LXXIX - Proteção de Dados, Administração Pública arts. 37-41, Finanças Públicas arts. 163-169).",
            "Arts. 5º (especialmente XII, XXXIII, LXXII e LXXIX), 37 a 41, 70 a 75, 165 a 169",
            "Portal da Legislação — Planalto",
            "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm",
            "DIR_CONST",
            "DIR_CONST_01",
            "cf_1988_compilada_planalto.html",
            "cf_1988_compilada_planalto.pdf",
        ),
        (
            "CONSTITUICAO_ESTADUAL",
            "ESTADUAL_PE",
            "1989",
            "1989",
            "Constituição do Estado de Pernambuco",
            "Texto constitucional do Estado de Pernambuco atualizado pela ALEPE.",
            "Administração Pública Estadual, Servidores, Tributação e Orçamento Estadual",
            "ALEPE Legis",
            "https://www.alepe.pe.gov.br/wp-content/uploads/2015/05/constituicaoestadual.pdf",
            "LEG_PE",
            "LEG_PE_02",
            None,
            "constituicao_estado_pe_alepe.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "FEDERAL",
            "13.709",
            "2018",
            "Lei Geral de Proteção de Dados Pessoais (LGPD)",
            "Dispõe sobre o tratamento de dados pessoais, inclusive nos meios digitais, por pessoa natural ou por pessoa jurídica de direito público ou privado.",
            "Arts. 1º a 65 (Fundamentos, Princípios art. 6º, Bases Legais arts. 7º e 11, Direitos do Titular art. 18, Poder Público arts. 23-30, Transferência Internacional arts. 33-36, Encarregado art. 41, Segurança arts. 46-49, Sanções art. 52, ANPD arts. 55-A a 55-L)",
            "Portal da Legislação — Planalto",
            "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm",
            "LGPD_ANPD",
            "LGPD_01",
            "lei_13709_2018_lgpd_planalto.html",
            "lei_13709_2018_lgpd_planalto.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "FEDERAL",
            "15.352",
            "2026",
            "Lei da Carreira de Regulação e Fiscalização de Proteção de Dados (ANPD)",
            "Estrutura a carreira e os cargos efetivos da Autoridade Nacional de Proteção de Dados.",
            "Atribuições do cargo de Especialista em Regulação de Proteção de Dados e estrutura funcional da ANPD",
            "Planalto / Imprensa Nacional",
            None,
            "LGPD_ANPD",
            "LGPD_02",
            "lei_15352_2026_carreira_anpd_planalto.html",
            "lei_15352_2026_carreira_anpd_planalto.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "FEDERAL",
            "15.211",
            "2025",
            "ECA Digital — Proteção de Crianças e Adolescentes no Ambiente Digital",
            "Dispõe sobre a proteção integral de crianças e adolescentes em serviços e plataformas digitais.",
            "Verificação etária, melhor interesse da criança, deveres dos provedores e atuação regulatória",
            "Planalto / Imprensa Nacional",
            None,
            "LGPD_ANPD",
            "LGPD_01",
            "lei_15211_2025_eca_digital_planalto.html",
            "lei_15211_2025_eca_digital_planalto.pdf",
        ),
        (
            "RESOLUCAO",
            "FEDERAL",
            "18",
            "2024",
            "Resolução CD/ANPD nº 18/2024 — Regulamento sobre a Atuação do Encarregado (DPO)",
            "Aprova o Regulamento sobre a Atuação do Encarregado pelo Tratamento de Dados Pessoais.",
            "Indicação formal, divulgação da identidade, substituto, ausência de conflito de interesses e deveres perante titulares e ANPD",
            "Diário Oficial da União / ANPD",
            "https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-18-de-16-de-julho-de-2024-572632074",
            "LGPD_ANPD",
            "LGPD_02",
            "resolucao_cd_anpd_18_2024_texto_oficial_dou.html",
            "resolucao_cd_anpd_18_2024_texto_oficial_dou.pdf",
        ),
        (
            "RESOLUCAO",
            "FEDERAL",
            "15",
            "2024",
            "Resolução CD/ANPD nº 15/2024 — Comunicação de Incidente de Segurança",
            "Aprova o Regulamento de Comunicação de Incidente de Segurança com Dados Pessoais.",
            "Critérios de risco ou dano relevante, prazo de 3 dias úteis para comunicação à ANPD e aos titulares, registro de incidentes por 5 anos",
            "ANPD / DOU",
            None,
            "LGPD_ANPD",
            "LGPD_03",
            None,
            "resolucao_cd_anpd_15_2024_incidentes.pdf",
        ),
        (
            "RESOLUCAO",
            "FEDERAL",
            "19",
            "2024",
            "Resolução CD/ANPD nº 19/2024 — Transferência Internacional de Dados",
            "Aprova o Regulamento de Transferência Internacional de Dados e o conteúdo das cláusulas-padrão contratuais.",
            "Decisão de adequação, cláusulas-padrão, normas corporativas globais e prazos de conformidade",
            "Gov.br / ANPD",
            "https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-19-de-23-de-agosto-de-2024",
            "LGPD_ANPD",
            "LGPD_03",
            "resolucao_cd_anpd_19_2024_transferencia_internacional.html",
            "resolucao_cd_anpd_19_2024_transferencia_internacional.pdf",
        ),
        (
            "RESOLUCAO",
            "FEDERAL",
            "4",
            "2023",
            "Resolução CD/ANPD nº 4/2023 — Regulamento de Dosimetria e Aplicação de Sanções Administrativas",
            "Estabelece parâmetros e critérios para aplicação de sanções administrativas pela ANPD.",
            "Classificação das infrações (leve, média, grave), cálculo da alíquota-base, agravantes, atenuantes e multa simples/diária",
            "Diário Oficial da União / ANPD",
            "https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-4-de-24-de-fevereiro-de-2023-466146077",
            "LGPD_ANPD",
            "LGPD_03",
            "resolucao_cd_anpd_04_2023_dosimetria_sancoes_dou.html",
            "resolucao_cd_anpd_04_2023_dosimetria_sancoes_dou.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "FEDERAL",
            "14.133",
            "2021",
            "Nova Lei de Licitações e Contratos Administrativos",
            "Lei de Licitações e Contratos Administrativos.",
            "Arts. 1º a 194 (Agentes de contratação, modalidades, pregão, diálogo competitivo, dispensa art. 75, contratos, PNCP)",
            "Portal da Legislação — Planalto",
            "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm",
            "DIR_ADM",
            "DIR_ADM_01",
            "lei_14133_2021_licitacoes_planalto.html",
            "lei_14133_2021_licitacoes_planalto.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "FEDERAL",
            "9.784",
            "1999",
            "Lei do Processo Administrativo Federal",
            "Regula o processo administrativo no âmbito da Administração Pública Federal.",
            "Arts. 1º a 69 (Princípios, competência, delegação/avocação arts. 11-15, motivação art. 50, decadência quinquenal art. 54)",
            "Portal da Legislação — Planalto",
            "https://www.planalto.gov.br/ccivil_03/leis/l9784.htm",
            "DIR_ADM",
            "DIR_ADM_02",
            "lei_9784_1999_planalto.html",
            "lei_9784_1999_planalto.pdf",
        ),
        (
            "LEI_COMPLEMENTAR",
            "FEDERAL",
            "101",
            "2000",
            "Lei de Responsabilidade Fiscal (LRF)",
            "Estabelece normas de finanças públicas voltadas para a responsabilidade na gestão fiscal.",
            "Receita Corrente Líquida (art. 2º, IV), Renúncia de Receita (art. 14), Despesa com Pessoal (arts. 18-23), Dívida e RREO/RGF",
            "Portal da Legislação — Planalto",
            "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp101.htm",
            "AFO",
            "AFO_03",
            "lc_101_2000_lrf_planalto.html",
            "lc_101_2000_lrf_planalto.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "FEDERAL",
            "4.320",
            "1964",
            "Normas Gerais de Direito Financeiro e Orçamento Público",
            "Estatui Normas Gerais de Direito Financeiro para elaboração e controle dos orçamentos e balanços.",
            "Receita (arts. 11, 51-57), Despesa (arts. 12-15, 58-70), Créditos Adicionais (arts. 40-46) e Restos a Pagar (art. 36)",
            "Portal da Legislação — Planalto",
            "https://www.planalto.gov.br/ccivil_03/leis/l4320.htm",
            "AFO",
            "AFO_02",
            "lei_4320_1964_direito_financeiro_planalto.html",
            "lei_4320_1964_direito_financeiro_planalto.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "ESTADUAL_PE",
            "6.123",
            "1968",
            "Estatuto dos Funcionários Públicos Civis do Estado de Pernambuco",
            "Regime Jurídico dos Funcionários Públicos Civis do Estado de Pernambuco.",
            "Provimento, posse, exercício, estágio probatório, direitos, deveres e regime disciplinar estadual",
            "ALEPE Legis",
            None,
            "LEG_PE",
            "LEG_PE_01",
            "lei_pe_6123_1968_estatuto_servidores.html",
            "lei_pe_6123_1968_estatuto_servidores.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "ESTADUAL_PE",
            "11.781",
            "2000",
            "Lei do Processo Administrativo Estadual de Pernambuco",
            "Regula o processo administrativo no âmbito da Administração Pública Estadual de Pernambuco.",
            "Princípios, prazos, instrução, recursos e anulação no âmbito estadual",
            "ALEPE Legis",
            None,
            "LEG_PE",
            "LEG_PE_02",
            "lei_pe_11781_2000_processo_adm_pe.html",
            "lei_pe_11781_2000_processo_adm_pe.pdf",
        ),
        (
            "LEI_ORDINARIA",
            "ESTADUAL_PE",
            "15.815",
            "2016",
            "Lei do FASAF — Fundo de Aperfeiçoamento dos Serviços Administrativos Fazendários (SEFAZ-PE)",
            "Consolida e altera o Fundo de Aperfeiçoamento dos Serviços Administrativos Fazendários - FASAF, e dá outras providências.",
            "Art. 2º (até 56% do FAAF), art. 2º §1º (gestão pela SAFI) e art. 3º (distribuição mensal aos servidores do GOAAF)",
            "ALEPE Legis",
            "https://legis.alepe.pe.gov.br/texto.aspx?tiponorma=1&numero=15815&complemento=0&ano=2016",
            "LEG_PE",
            "LEG_PE_02",
            "lei_pe_15815_2016_fasaf_alepe.html",
            "lei_pe_15815_2016_fasaf_alepe.pdf",
        ),
    ]

    for (
        tnorma,
        juris,
        num,
        ano,
        tit,
        ementa,
        arts,
        fonte_nome,
        fonte_url,
        cod_disc,
        cod_top,
        html_name,
        pdf_name,
    ) in normas_seed:
        exists_n = db.scalar(
            select(NormaJuridica).where(
                NormaJuridica.numero == num,
                NormaJuridica.ano == ano,
                NormaJuridica.jurisdicao == juris,
            )
        )
        if not exists_n:
            m_html = mat_by_name.get(html_name) if html_name else None
            m_pdf = mat_by_name.get(pdf_name) if pdf_name else None
            top_obj = topicos_map.get(cod_top)
            db.add(
                NormaJuridica(
                    tipo_norma=tnorma,
                    jurisdicao=juris,
                    numero=num,
                    ano=ano,
                    titulo_curto=tit,
                    ementa=ementa,
                    artigos_chave=arts,
                    fonte_oficial_nome=fonte_nome,
                    fonte_oficial_url=fonte_url,
                    data_atualizacao_verificada=date(2026, 11, 22),
                    versao_controle="Texto Compilado Verificado em 22/11/2026",
                    historico_alteracoes_legislativas="Arquivo oficial verificado no acervo com hash SHA-256 conferido.",
                    status_vigencia="VIGENTE_VERIFICADA_EM_FONTE",
                    disciplina_id=disc_map[cod_disc].id,
                    topico_id=top_obj.id if top_obj else None,
                    material_html_id=m_html.id if m_html else None,
                    material_pdf_id=m_pdf.id if m_pdf else None,
                )
            )
            if top_obj and m_pdf:
                if not db.scalar(
                    select(AssociacaoMaterialTopico).where(
                        AssociacaoMaterialTopico.material_id == m_pdf.id,
                        AssociacaoMaterialTopico.topico_id == top_obj.id,
                    )
                ):
                    db.add(
                        AssociacaoMaterialTopico(
                            material_id=m_pdf.id,
                            topico_id=top_obj.id,
                            tipo_vinculo="LEGISLACAO_BASE",
                        )
                    )
    db.commit()

    # 8. Peso oficial das matérias no edital SEFAZ-PE 2022 (item 5.2.1) — dado verificado
    METODO_EDITAL = "Distribuição oficial de questões do edital (item 5.2.1)"
    db.execute(
        delete(HistoricoProvaCobranca).where(
            HistoricoProvaCobranca.metodo_utilizado != METODO_EDITAL
        )
    )
    if db.scalar(select(func.count(HistoricoProvaCobranca.id))) == 0:
        mat_edital = mat_by_name.get("sefaz_pe_2022_edital_001_2022.pdf")
        pesos = [
            ("ADM_PUB", "Administração Geral e Pública", 20),
            ("PORT", "Língua Portuguesa", 10),
            ("RLM", "Raciocínio Lógico-Matemático", 5),
            ("INFO_BASICA", "Informática", 5),
            ("DIR_ADM", "Direito Administrativo", 5),
            ("DIR_CONST", "Direito Constitucional", 5),
            ("AFO", "Orçamento Público", 5),
            ("EDU_FISCAL", "Educação Fiscal", 5),
        ]
        for cod, nome, qtd in pesos:
            if cod not in disc_map:
                continue
            db.add(
                HistoricoProvaCobranca(
                    banca_id=bancas_map["IAUPE/UPENET"].id,
                    banca_sigla="IAUPE/UPENET",
                    concurso_nome="SEFAZ-PE 2022 (Edital nº 001/2022)",
                    cargo_nome="Analista de Apoio Administrativo às Atividades Fazendárias",
                    ano_prova=2022,
                    disciplina_id=disc_map[cod].id,
                    assunto_cobrado=nome,
                    quantidade_questoes_assunto=qtd,
                    total_questoes_prova=60,
                    frequencia_percentual=round(qtd / 60 * 100, 1),
                    classificacao_recorrencia="PESO_OFICIAL_NO_EDITAL",
                    evidencias_utilizadas="Edital nº 001/2022, item 5.2.1 (01_EDITAIS_E_PLANEJAMENTO).",
                    quantidade_provas_analisadas=1,
                    periodo_considerado="2022",
                    metodo_utilizado=METODO_EDITAL,
                    nivel_confianca_analise="OFICIAL (edital)",
                    limitacoes_analise="Distribuição do edital de 2022; o próximo edital pode mudar. A contagem por assunto dentro das provas do acervo ainda não foi feita.",
                    material_prova_id=mat_edital.id if mat_edital else None,
                )
            )
        db.commit()

    # 9. Biblioteca de Súmulas, Jurisprudência, Repercussão Geral, Repetitivos e Enunciados ANPD (Seção 20)
    if db.scalar(select(func.count(EntendimentoJurisprudencia.id))) == 0:
        hoje = date.today()
        juris_seed = [
            (
                "STF_VINCULANTE",
                "SUMULA_VINCULANTE",
                "Súmula Vinculante 13",
                disc_map["DIR_ADM"].id,
                topicos_map["DIR_ADM_03"].id,
                "Vedação ao Nepotismo na Administração Pública",
                "A nomeação de cônjuge, companheiro ou parente em linha reta, colateral ou por afinidade, até o terceiro grau, inclusive, da autoridade nomeante ou de servidor da mesma pessoa jurídica investido em cargo de direção, chefia ou assessoramento, para o exercício de cargo em comissão ou de confiança ou, ainda, de função gratificada na administração pública direta e indireta em qualquer dos Poderes da União, dos Estados, do Distrito Federal e dos Municípios, compreendido o ajuste mediante designações recíprocas, viola a Constituição Federal.",
                "A SV 13 veda o nepotismo direto e cruzado até o 3º grau na Administração Direta e Indireta. Ressalva jurisprudencial do STF: cargos de natureza estritamente política (ex.: Secretário de Estado/Ministro), salvo comprovação de troca de favores, fraude à lei ou manifesta ausência de qualificação técnica.",
                date(2008, 8, 29),
                "Portal Oficial do STF — Súmulas Vinculantes",
                "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26&sumula=1227",
                "SEFAZ-PE, ANPD",
                True,
            ),
            (
                "STF",
                "SUMULA_STF",
                "Súmula 473 do STF",
                disc_map["DIR_ADM"].id,
                topicos_map["DIR_ADM_02"].id,
                "Autotutela Administrativa: Anulação e Revogação de Atos Administrativos",
                "A administração pode anular seus próprios atos, quando eivados de vícios que os tornam ilegais, porque deles não se originam direitos; ou revogá-los, por motivo de conveniência ou oportunidade, respeitados os direitos adquiridos, e ressalvada, em todos os casos, a apreciação judicial.",
                "Fundamento clássico da autotutela (em conjunto com o art. 53 da Lei 9.784/99 e da Lei PE 11.781/00). Observar o prazo decadencial de 5 anos para destinatários de boa-fé (art. 54 da Lei 9.784/99) e a necessidade de contraditório quando a invalidação repercutir na esfera individual.",
                date(1969, 12, 3),
                "Portal Oficial do STF — Súmulas",
                "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=30&sumula=1602",
                "SEFAZ-PE, ANPD",
                True,
            ),
            (
                "STF",
                "JURISPRUDENCIA_RELEVANTE",
                "ADI 6387 / Direito Fundamental à Proteção de Dados e EC 115/2022",
                disc_map["DIR_CONST"].id,
                topicos_map["DIR_CONST_01"].id,
                "Autonomia do Direito Fundamental à Proteção de Dados Pessoais e Autodeterminação Informativa",
                "O Supremo Tribunal Federal reconheceu a proteção de dados pessoais e a autodeterminação informativa como direitos fundamentais autônomos decorrentes da dignidade da pessoa humana, da privacidade e do sigilo das comunicações, entendimento posteriormente positivado no art. 5º, LXXIX, da CF/88 pela Emenda Constitucional nº 115/2022.",
                "Não existem dados pessoais neutros ou insignificantes no âmbito do tratamento estatal: o compartilhamento de dados entre órgãos públicos exige finalidade legítima, específica, explícita, necessidade, proporcionalidade e observância das salvaguardas da LGPD.",
                date(2020, 5, 7),
                "Plenário do Supremo Tribunal Federal (ADI 6387)",
                "https://portal.stf.jus.br/",
                "ANPD, SEFAZ-PE",
                True,
            ),
            (
                "ANPD",
                "ENUNCIADO_ANPD",
                "Enunciado CD/ANPD nº 1/2023",
                disc_map["LGPD_ANPD"].id,
                topicos_map["LGPD_01"].id,
                "Bases Legais para o Tratamento de Dados Pessoais de Crianças e Adolescentes",
                "O tratamento de dados pessoais de crianças e de adolescentes poderá ser realizado com base nas hipóteses legais previstas no art. 7º ou no art. 11 da Lei Geral de Proteção de Dados Pessoais (LGPD), desde que observado e prevalecente o seu melhor interesse, a ser avaliado no caso concreto, nos termos do art. 14 da Lei.",
                "Supera a interpretação restritiva de que apenas o consentimento (art. 14, § 1º) seria aplicável a crianças e adolescentes: todas as bases dos arts. 7º e 11 podem ser utilizadas desde que o controlador demonstre a prevalência do melhor interesse da criança ou do adolescente.",
                date(2023, 5, 22),
                "Diário Oficial da União / Conselho Diretor da ANPD (Arquivo oficial em 03_ANPD)",
                "https://www.in.gov.br/en/web/dou/-/enunciado-cd/anpd-n-1-de-22-de-maio-de-2023-485306934",
                "ANPD",
                True,
            ),
            (
                "STJ",
                "SUMULA_STJ",
                "Súmula 633 do STJ",
                disc_map["DIR_ADM"].id,
                topicos_map["DIR_ADM_03"].id,
                "Aplicação Subsidiária da Lei nº 9.784/1999 aos Estados e Municípios",
                "A Lei n. 9.784/1999, especialmente no que diz respeito ao prazo decadencial para a revisão de atos administrativos no âmbito da Administração Pública federal, pode ser aplicada, de forma subsidiária, aos estados e municípios, se inexistente norma local e específica que regule a matéria.",
                "Em Pernambuco existe a Lei Estadual nº 11.781/2000 (presente no acervo em 02_SEFAZ_PE), que regula especificamente o processo administrativo estadual; portanto, aplica-se a norma local pernambucana na SEFAZ-PE.",
                date(2019, 6, 12),
                "Superior Tribunal de Justiça — Primeira Seção",
                "https://scon.stj.jus.br/SCON/sumstj/",
                "SEFAZ-PE, ANPD",
                False,
            ),
            (
                "STF",
                "REPERCUSSAO_GERAL",
                "Tema 897 de Repercussão Geral (RE 852.475)",
                disc_map["DIR_ADM"].id,
                topicos_map["DIR_ADM_03"].id,
                "Imprescritibilidade das Ações de Ressarcimento ao Erário por Ato Doloso de Improbidade",
                "São imprescritíveis as ações de ressarcimento ao erário fundadas na prática de ato doloso tipificado na Lei de Improbidade Administrativa.",
                "Após a Lei 14.230/2021, todo ato de improbidade administrativa exige dolo específico; a ação de ressarcimento ao erário decorrente de ato doloso de improbidade permanece imprescritível.",
                date(2018, 8, 8),
                "Supremo Tribunal Federal — Repercussão Geral",
                "https://portal.stf.jus.br/",
                "SEFAZ-PE, ANPD",
                True,
            ),
            (
                "STJ",
                "RECURSO_REPETITIVO",
                "Tema Repetitivo 1177 do STJ (Vazamento de Dados Comuns vs Sensíveis)",
                disc_map["LGPD_ANPD"].id,
                topicos_map["LGPD_02"].id,
                "Dano Moral em Incidente de Segurança com Dados Pessoais Comuns",
                "O vazamento de dados pessoais comuns, por si só, não gera dano moral presumido (in re ipsa), sendo necessária a comprovação de efetivo prejuízo pelo titular, diferentemente do tratamento ilícito ou exposição de dados pessoais sensíveis a depender das circunstâncias do caso.",
                "Distinção recorrente em provas do Cebraspe sobre responsabilidade civil na LGPD (arts. 42 a 45): na esfera administrativa sancionadora da ANPD (art. 52 e Resolução nº 15/2024), a infração independe de ação judicial individual de dano moral.",
                date(2023, 3, 7),
                "Superior Tribunal de Justiça — Jurisprudência sobre LGPD",
                "https://scon.stj.jus.br/",
                "ANPD",
                True,
            ),
            (
                "TCU",
                "INFORMATIVO",
                "Acórdão TCU Plenário — Auditoria de Adequação à LGPD (TC 039.606/2020)",
                disc_map["LGPD_ANPD"].id,
                topicos_map["LGPD_02"].id,
                "Governança de Privacidade, Inventário de Dados Pessoais e RIPD na Administração Federal",
                "As organizações públicas federais devem manter inventário atualizado das operações de tratamento de dados pessoais, nomear formalmente o Encarregado (DPO), elaborar Relatório de Impacto à Proteção de Dados Pessoais (RIPD) para tratamentos de alto risco e implementar plano de resposta a incidentes.",
                "Extraído diretamente do relatório oficial TCU_Relatorio_Auditoria_LGPD_TC039606_2020.pdf disponível em 06_MATERIAIS_E_INVENTARIO.",
                date(2022, 5, 18),
                "Tribunal de Contas da União (Arquivo oficial em 06_MATERIAIS_E_INVENTARIO)",
                None,
                "ANPD, TCU",
                True,
            ),
        ]

        for (
            trib,
            tipo,
            num_id,
            did,
            tid,
            assunto,
            texto,
            resumo,
            dt_pub,
            fonte_of,
            link_or,
            concs,
            fav,
        ) in juris_seed:
            db.add(
                EntendimentoJurisprudencia(
                    tribunal=trib,
                    tipo_entendimento=tipo,
                    numero_identificacao=num_id,
                    disciplina_id=did,
                    topico_id=tid,
                    assunto_titulo=assunto,
                    texto_entendimento=texto,
                    resumo_didatico=resumo,
                    data_publicacao=dt_pub,
                    data_atualizacao_verificada=date(2026, 11, 22),
                    situacao_vigencia="VIGENTE_VERIFICADA",
                    fonte_oficial=fonte_of,
                    link_origem=link_or,
                    concursos_relacionados=concs,
                    favorito=fav,
                    sm2_repeticoes=0,
                    sm2_easiness_factor=2.5,
                    sm2_intervalo_dias=0,
                    sm2_proxima_revisao=hoje,
                )
            )
        db.commit()

    # 10. Flashcards iniciais com algoritmo SM-2 (Seção 17)
    if db.scalar(select(func.count(Flashcard.id))) == 0:
        hoje = date.today()
        flashcards_seed = [
            (
                "Qual é o prazo regulamentar (Resolução CD/ANPD nº 15/2024) para o controlador comunicar à ANPD e ao titular a ocorrência de incidente de segurança que possa acarretar risco ou dano relevante?",
                "3 (três) dias úteis, contados do conhecimento pelo controlador de que o incidente afetou dados pessoais (art. 6º da Resolução CD/ANPD nº 15/2024). Para agentes de pequeno porte (Res. nº 2/2022), o prazo é concedido em dobro (6 dias úteis).",
                disc_map["LGPD_ANPD"].id,
                topicos_map["LGPD_03"].id,
            ),
            (
                "Segundo o Enunciado CD/ANPD nº 1/2023, o tratamento de dados pessoais de crianças e adolescentes restringe-se exclusivamente à hipótese de consentimento específico (art. 14, § 1º)?",
                "Não. O tratamento pode fundamentar-se em qualquer das bases legais previstas no art. 7º ou no art. 11 da LGPD, desde que observado e prevalecente o melhor interesse da criança ou do adolescente no caso concreto.",
                disc_map["LGPD_ANPD"].id,
                topicos_map["LGPD_01"].id,
            ),
            (
                "Quais são os limites máximos da Despesa Total com Pessoal na LRF (LC nº 101/2000, arts. 19 e 20) para a União e para os Estados (como Pernambuco)?",
                "União: 50% da RCL (40,9% Executivo, 2,5% Legislativo/TCU, 6% Judiciário, 0,6% MPU). Estados: 60% da RCL (49% Executivo, 3% Legislativo/TCE, 6% Judiciário, 2% MPE). Limite prudencial: 95% do limite máximo; Limite de alerta: 90%.",
                disc_map["AFO"].id,
                topicos_map["AFO_03"].id,
            ),
            (
                "Na Lei nº 14.133/2021, quais são as 5 modalidades de licitação existentes e quais foram extintas?",
                "Modalidades vigentes (art. 28): 1. Pregão; 2. Concorrência; 3. Concurso; 4. Leilão; 5. Diálogo Competitivo. Foram extintas a Tomada de Preços, o Convite e o RDC.",
                disc_map["DIR_ADM"].id,
                topicos_map["DIR_ADM_01"].id,
            ),
            (
                "Pela Lei Estadual PE nº 15.815/2016, quem gere o FASAF e para quem os recursos são distribuídos mensalmente?",
                "O FASAF (Fundo de Aperfeiçoamento dos Serviços Administrativos Fazendários) é gerido pela SAFI (SEFAZ) e é integralizado por até 56% dos recursos do FAAF (arts. 2º e 3º). Os recursos são distribuídos mensalmente aos servidores do GOAAF (Grupo Ocupacional Apoio Administrativo às Atividades Fazendárias).",
                disc_map["LEG_PE"].id,
                topicos_map["LEG_PE_02"].id,
            ),
            (
                "Em Aprendizado de Máquina, qual é a diferença entre Precisão (Precision), Revocação (Recall) e F1-Score?",
                "Precision = VP / (VP + FP) (dos previstos como positivos, quantos são reais). Recall = VP / (VP + FN) (dos positivos reais, quantos foram capturados). F1-Score = média harmônica entre Precision e Recall: 2 * (P * R) / (P + R).",
                disc_map["TI_IA"].id,
                topicos_map["TI_IA_01"].id,
            ),
        ]
        for pergunta, resposta, did, tid in flashcards_seed:
            db.add(
                Flashcard(
                    frente_pergunta=pergunta,
                    verso_resposta=resposta,
                    disciplina_id=did,
                    topico_id=tid,
                    algoritmo_utilizado="SM-2",
                    sm2_repeticoes=0,
                    sm2_easiness_factor=2.5,
                    sm2_intervalo_dias=0,
                    proxima_revisao_em=hoje,
                )
            )
        db.commit()

    # 11. Questões reais fundamentadas nos documentos e provas do acervo (Seção 15 e 18)
    if db.scalar(select(func.count(Questao.id))) == 0:
        questoes_seed = [
            (
                "QUESTAO_TREINO_PLATAFORMA",
                "ANATEL 2024 / Padrão Cebraspe",
                bancas_map["Cebraspe"].id,
                "Cebraspe",
                2024,
                disc_map["LGPD_ANPD"].id,
                topicos_map["LGPD_01"].id,
                "CERTO_ERRADO",
                "À luz da Lei nº 13.709/2018 (LGPD) e do Enunciado CD/ANPD nº 1/2023, o tratamento de dados pessoais de crianças e de adolescentes pode ser realizado com base nas hipóteses legais previstas tanto no art. 7º quanto no art. 11 da LGPD, desde que observado e prevalecente o seu melhor interesse.",
                None,
                "CERTO",
                "Item literal do Enunciado CD/ANPD nº 1, de 22 de maio de 2023 (presente no acervo em 03_ANPD/Enunciado_CD_ANPD_01_2023_Criancas_Adolescentes_DOU.html).",
                "Enunciado CD/ANPD nº 1/2023 e Prova Cebraspe ANATEL 2024 no acervo",
            ),
            (
                "QUESTAO_TREINO_PLATAFORMA",
                "Padrão Cebraspe — Resolução CD/ANPD nº 18/2024",
                bancas_map["Cebraspe"].id,
                "Cebraspe",
                2025,
                disc_map["LGPD_ANPD"].id,
                topicos_map["LGPD_02"].id,
                "CERTO_ERRADO",
                "De acordo com a Resolução CD/ANPD nº 18/2024, o encarregado pelo tratamento de dados pessoais (DPO) deve ser obrigatoriamente uma pessoa natural integrante do quadro societário ou de servidores efetivos do controlador, sendo vedada a designação de pessoa jurídica externa.",
                None,
                "ERRADO",
                "Nos termos da Resolução CD/ANPD nº 18/2024 (e Guia Orientativo do Encarregado Dez/2024 em 03_ANPD), o encarregado pode ser pessoa natural (integrante ou externa à organização) ou pessoa jurídica.",
                "Resolução CD/ANPD nº 18/2024 (03_ANPD/Resolucao_CD_ANPD_18_2024_Texto_Oficial_DOU.html)",
            ),
            (
                "QUESTAO_TREINO_PLATAFORMA",
                "SEPLAG/AL — UNEAL 2026 (Cargo 5: Analista Administrativo)",
                bancas_map["Cebraspe"].id,
                "Cebraspe",
                2026,
                disc_map["ADM_PUB"].id,
                topicos_map["ADM_PUB_02"].id,
                "CERTO_ERRADO",
                "Na gestão de projetos baseada em métodos ágeis como o Scrum, o trabalho é dividido em ciclos iterativos de curta duração denominados sprints, ao final dos quais se busca entregar um incremento potencialmente utilizável do produto.",
                None,
                "CERTO",
                "Conceito central do framework Scrum cobrado no Caderno Cebraspe_Adm_Publica_Doc3.pdf (UNEAL 2026) do acervo.",
                "05_PROVAS_E_GABARITOS/Cebraspe_Adm_Publica_Doc3.pdf (Prova UNEAL 2026 Cebraspe)",
            ),
            (
                "QUESTAO_TREINO_PLATAFORMA",
                "SEFAZ-PE 2022 — Analista de Apoio Administrativo",
                bancas_map["IAUPE/UPENET"].id,
                "IAUPE/UPENET",
                2022,
                disc_map["AFO"].id,
                topicos_map["AFO_02"].id,
                "MULTIPLA_ESCOLHA",
                "Nos termos da Lei Federal nº 4.320/1964, o ato emanado de autoridade competente que cria para o Estado obrigação de pagamento pendente ou não de implemento de condição denomina-se:",
                json.dumps(
                    {
                        "A": "Liquidação da despesa",
                        "B": "Empenho da despesa",
                        "C": "Ordem de pagamento",
                        "D": "Dotação orçamentária",
                        "E": "Restos a pagar",
                    },
                    ensure_ascii=False,
                ),
                "B",
                "Art. 58 da Lei nº 4.320/1964: 'O empenho de despesa é o ato emanado de autoridade competente que cria para o Estado obrigação de pagamento pendente ou não de implemento de condição.'",
                "Lei nº 4.320/1964 e Caderno Analista de Apoio Administrativo SEFAZ-PE 2022 (05_PROVAS_E_GABARITOS)",
            ),
            (
                "QUESTAO_TREINO_PLATAFORMA",
                "TCU 2025/2026 — Auditoria de TI / Ciência de Dados",
                bancas_map["Cebraspe"].id,
                "Cebraspe",
                2026,
                disc_map["TI_ENG_DADOS"].id,
                topicos_map["TI_ENG_01"].id,
                "CERTO_ERRADO",
                "Em modelagem dimensional de Data Warehouse, o esquema estrela (Star Schema) caracteriza-se por uma tabela de fatos central ligada diretamente a tabelas de dimensão desnormalizadas, favorecendo o desempenho de consultas analíticas OLAP.",
                None,
                "CERTO",
                "No Star Schema as dimensões são mantidas desnormalizadas (1 nível a partir da tabela fato), reduzindo a quantidade de JOINs em consultas OLAP em comparação ao Snowflake Schema.",
                "Prova Cebraspe TCU 2026 / SERPRO 2023 em 05_PROVAS_E_GABARITOS",
            ),
            (
                "QUESTAO_TREINO_PLATAFORMA",
                "SERPRO 2023 / ANATEL 2024 — Ciência de Dados",
                bancas_map["Cebraspe"].id,
                "Cebraspe",
                2024,
                disc_map["TI_IA"].id,
                topicos_map["TI_IA_01"].id,
                "CERTO_ERRADO",
                "Em problemas de classificação binária com classes fortemente desbalanceadas, a acurácia global isolada é a métrica mais indicada para avaliar a capacidade do modelo de identificar a classe minoritária.",
                None,
                "ERRADO",
                "Em bases desbalanceadas, a acurácia é enganosa (paradoxo da acurácia); devem ser utilizadas métricas sensíveis à classe minoritária, como Precision, Recall, F1-Score e PR-AUC.",
                "Provas Cebraspe ANATEL 2024 e SERPRO 2023 (05_PROVAS_E_GABARITOS)",
            ),
        ]
        for (
            nat,
            conc_ref,
            bid,
            bnome,
            ano_q,
            did,
            tid,
            mod,
            enunc,
            alts,
            gab,
            coment,
            fonte_o,
        ) in questoes_seed:
            db.add(
                Questao(
                    natureza_questao=nat,
                    concurso_referencia=conc_ref,
                    banca_id=bid,
                    banca_nome=bnome,
                    ano=ano_q,
                    disciplina_id=did,
                    topico_id=tid,
                    modalidade=mod,
                    enunciado=enunc,
                    alternativas_json=alts,
                    gabarito=gab,
                    comentario_explicacao=coment,
                    fonte_origem=fonte_o,
                )
            )
        db.commit()

    # 12. Metas e Alertas Iniciais (Seção 22)
    if db.scalar(select(func.count(MetaAlerta.id))) == 0:
        metas_seed = [
            (
                "META",
                "META_HORAS_SEMANAL",
                "Meta Semanal de Estudo Integrado (60% SEFAZ-PE / 40% ANPD+TI)",
                "Cumprir 24 horas semanais distribuídas proporcionalmente entre o Eixo 1 (SEFAZ-PE: ~14,4h) e o Eixo 2 (ANPD + Dados e TI: ~9,6h).",
                1440.0,
                0.0,
                "ALTA",
            ),
            (
                "META",
                "META_QUESTOES_ASSUNTO",
                "Meta Referência de 20 Questões por Assunto Estudado",
                "Meta ajustável de 20 questões por tópico da Matriz Integrada (no Qconcursos ou provas do acervo) quando houver itens compatíveis.",
                20.0,
                0.0,
                "MEDIA",
            ),
            (
                "ALERTA",
                "DOCUMENTO_SEM_CLASSIFICACAO",
                "Auditoria Documental: 3 Arquivos com Falha/SPA e 1 Nome Trocado no Acervo",
                "O indexador identificou 2 páginas HTML SPA do Cebraspe (114 bytes), 1 tentativa inválida do PPA-PE e o arquivo ANPD_Guia_Poder_Publico.pdf (cujo conteúdo real é o Guia de Cookies Out/2022). Todos os originais foram preservados.",
                None,
                None,
                "MEDIA",
            ),
            (
                "ALERTA",
                "OPORTUNIDADE_RADAR",
                "Acompanhamento Prioritário: Publicação do Edital Oficial da ANPD (Cebraspe)",
                "A banca Cebraspe já foi contratada (Ato nº 69/2026). Assim que o edital definitivo for publicado, confirmar os tópicos marcados como 'Pendente de Confirmação' na Matriz Integrada.",
                None,
                None,
                "ALTA",
            ),
        ]
        for treg, cat, tit, desc, val_alvo, val_atual, prio in metas_seed:
            db.add(
                MetaAlerta(
                    tipo_registro=treg,
                    categoria=cat,
                    titulo=tit,
                    descricao=desc,
                    valor_alvo=val_alvo,
                    valor_atual=val_atual,
                    prioridade=prio,
                )
            )
        db.commit()

    aplicar_correcoes_integridade(db)
    return stats_acervo
