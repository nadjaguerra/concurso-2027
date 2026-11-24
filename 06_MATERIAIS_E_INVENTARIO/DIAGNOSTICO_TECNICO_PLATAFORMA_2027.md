# DIAGNÓSTICO TÉCNICO — PLATAFORMA CONCURSO 2027 (FASE 1)

**Data da inspeção:** 23/11/2026  
**Raiz oficial do projeto:** `C:\Users\nadja\OneDrive\Documents\2027 PLATAFORMA`  
**Fase do Plano de Execução:** Fase 1 — Diagnóstico técnico do projeto  
**Modo de execução:** Somente leitura (nenhum arquivo existente foi modificado, movido, renomeado ou excluído).

---

## 1. Resumo Executivo do Estado Real

A inspeção completa da raiz oficial confirma que **ainda não existe código-fonte de aplicação implementado** no diretório. Todo o conteúdo presente até o momento consiste em:
1. **Documentação mestre de especificação e plano de execução** na raiz (4 arquivos `.md`).
2. **Acervo documental de estudo, provas, legislação, relatórios de auditoria e inventários** distribuído exclusivamente nas **6 pastas principais do acervo** (217 arquivos, totalizando **221 arquivos** na raiz oficial).

Não há código residual, pacotes instalados (`node_modules`, `venv`), arquivos de configuração de aplicação (`package.json`, `pyproject.toml`, `.env`) ou banco de dados criado (`.sqlite`, `.db`). Isso garante um ponto de partida limpo ("greenfield" para o software, acoplado a um acervo documental já higienizado e auditado).

---

## 2. Inspeção dos Itens Obrigatórios da Fase 1

### 2.1 Linguagens, Frameworks e Versões
- **No projeto:** Nenhuma linguagem ou framework de aplicação foi instanciado ainda (0 arquivos `.js`, `.ts`, `.tsx`, `.py`, `.css`, `.json`, `.sql`).
- **Runtimes e ferramentas disponíveis no ambiente local (Windows):**
  - **Node.js:** `v24.22.0` (`C:\Program Files\nodejs\node.exe`), com suporte nativo confirmado ao módulo embutido `node:sqlite` (`DatabaseSync: true`).
  - **NPM:** `11.19.1` via `npm.cmd` *(observação técnica: `npm.ps1` é bloqueado pela política `ExecutionPolicy` do PowerShell no Windows; comandos devem invocar `npm.cmd` ou `node` diretamente)*.
  - **Python:** `Python 3.13.5` (`C:\Users\nadja\AppData\Local\Programs\Python\Python313\python.exe`), com módulo `sqlite3` nativo (`v3.49.1`).
  - **Git:** `git version 2.55.0.windows.5` (`C:\Program Files\Git\cmd\git.exe`). O diretório ainda não possui repositório Git inicializado (`.git` ausente).

### 2.2 Estrutura de Pastas Encontrada na Raiz Oficial

A raiz contém exatamente as **6 pastas principais do acervo** (além de 1 subpasta de backup dentro de `06_MATERIAIS_E_INVENTARIO`) e **4 arquivos Markdown na raiz**:

| Caminho Relativo | Tipo | Quantidade de Arquivos | Descrição do Estado Atual |
|---|---|---:|---|
| `.` (Raiz do projeto) | Diretório Raiz | 4 arquivos diretos | Contém `ESPECIFICACAO_COMPLETA_PLATAFORMA_2027.md`, `PLANO_DE_EXECUCAO_CODEX_2027.md`, `PROMPT_1_DOCUMENTACAO_MESTRE_CODEX.md` e `PROMPT_2_DESENVOLVIMENTO_CODEX.md`. |
| `01_EDITAIS_E_PLANEJAMENTO` | Pasta do Acervo | 8 | Editais (SEFAZ-PE 2022, SERPRO 2023, TCU 2025, SP Águas 2026), TR nº 111/2026 ANPD, Autorização Cebraspe ANPD e Planejamento Estratégico ANPD. |
| `02_SEFAZ_PE` | Pasta do Acervo | 12 | Constituição Estadual PE (PDF), legislação estadual PE (Leis 6.123/68, 11.781/00, 14.538/11, 15.815/16 FASAF em pares HTML+PDF, tentativa PPA 19.159/25) e guia PNEF Educação Fiscal (PDF). |
| `03_ANPD` | Pasta do Acervo | 65 | Legislação federal de proteção de dados/digital (LGPD, Marco Civil, ECA Digital, Lei 13.853/19, Lei 15.352/26, Decretos, Resoluções CD/ANPD, Notas Técnicas e Guias Orientativos em HTML e PDF). |
| `04_DISCIPLINAS_E_LEGISLACAO` | Pasta do Acervo | 44 | Constituição Federal de 1988 e legislação federal transversal (Direito Administrativo, Constitucional, AFO/LRF/Lei 4.320, Código Civil, LINDB, Lei das Estatais, Licitações 14.133/21, etc., em pares HTML+PDF). |
| `05_PROVAS_E_GABARITOS` | Pasta do Acervo | 56 | Provas e gabaritos oficiais em PDF (SEFAZ-PE 2022 Analista e Assistente, Cebraspe TI/Dados/Regulação, FGV, Cesgranrio/CNU 2024). |
| `06_MATERIAIS_E_INVENTARIO` | Pasta do Acervo | 32 | Inventário geral (`.csv`, `.xlsx`, `.ndjson` e backups em `BACKUP_INVENTARIOS_20261122`), 14 relatórios Markdown anteriores, manuais (MCASP 11ª ed., MTO 2027, TCU, CGU) e arquivos de consulta. |

> **Nota sobre pastas antigas:** O relatório histórico `DIAGNOSTICO_ESTRUTURA_ATUAL_2027.md` (de 22/11/2026) mencionava 13 pastas vazias paralelas (`01_DOCUMENTOS`, `10_PLATAFORMA`, etc.). A inspeção física atual confirma que essas pastas vazias já não existem no disco; restam apenas as 6 pastas oficiais do acervo definidas na Seção 7 da Especificação.

### 2.3 Distribuição de Arquivos por Extensão (221 arquivos no total)

| Extensão | Quantidade | Observação |
|---|---:|---|
| `.pdf` | 143 | Editais, provas, gabaritos, guias, manuais e versões PDF geradas a partir de normas HTML. |
| `.html` | 55 | Textos normativos compilados (Planalto, ALEPE, DOU, Gov.br) e páginas oficiais de consulta. |
| `.md` | 18 | 4 documentos mestres na raiz + 14 relatórios e diagnósticos documentais em `06_MATERIAIS_E_INVENTARIO`. |
| `.xlsx` | 2 | `INVENTARIO_GERAL_CONCURSO_2027.xlsx` + 1 cópia em `BACKUP_INVENTARIOS_20261122`. |
| `.csv` | 2 | `INVENTARIO_GERAL_CONCURSO_2027.csv` + 1 cópia em `BACKUP_INVENTARIOS_20261122`. |
| `.ndjson` | 1 | `INVENTARIO_GERAL_CONCURSO_2027.xlsx.inspect.ndjson` (artefato de inspeção em `06_MATERIAIS_E_INVENTARIO`). |

### 2.4 Entrypoint, Rotas, Componentes, Scripts e Dependências
- **Entrypoint / Rotas / Componentes:** **Ausentes (0 implementados).**
- **Scripts e Comandos de Build/Execução:** **Ausentes.**
- **Dependências Instaladas:** **Nenhuma.**

### 2.5 Banco de Dados e Persistência
- **Estado atual:** Não há banco de dados estruturado da aplicação.
- **Dados estruturados existentes no acervo:** O arquivo `06_MATERIAIS_E_INVENTARIO/INVENTARIO_GERAL_CONCURSO_2027.csv` (244 linhas / ~190 registros catalogados com metadados ricos: Título, Classificação de utilidade, Concurso real, Cargo real, Banca confirmada, Disciplina, Órgão, Ano, Tipo de documento, Situação do arquivo, Fonte confirmada, URL, Nome do arquivo, Caminho local, Formato, Tamanho, Data de download, Vigência, Hash SHA-256, Justificativa e Providência necessária) constitui a fonte primária validada para semear (seed) o catálogo inicial do **Banco de Conteúdos e Materiais**, **Concursos/Editais** e **Legislação** sem inventar dados.

### 2.6 Testes Automatizados
- **Estado atual:** **Ausentes (0 testes).**

---

## 3. Levantamento de Funcionalidades (Existentes, Parciais e Ausentes)

| Módulo / Funcionalidade (Especificação Seção 4) | Estado Técnico Atual | Observação |
|---|---|---|
| **1. Meu Dia (Dashboard e rotina diária)** | **Ausente** | Regras pedagógicas definidas na especificação; requer implementação integral. |
| **2. Cronograma Inteligente** | **Ausente** | Depende de validação prévia da Matriz Integrada de Conteúdos (Regra 2.2.7 e 4.7). |
| **3. Disciplinas e 4. Conteúdos (Matriz Integrada)** | **Ausente no software / Base documental disponível** | O Edital SEFAZ-PE 001/2022 e o TR ANPD 111/2026 + provas de referência estão no acervo para extração rastreável da matriz integrada. |
| **5. Revisões Espaçadas (D1/D7/D15/D30/D60)** | **Ausente** | Algoritmo adaptativo e registro manual a implementar. |
| **6. Questões, 7. Caderno de Erros e 8. Simulados** | **Ausente no software / Provas PDF disponíveis** | 56 PDFs de provas e gabaritos reais no acervo; registro manual e referência ao Qconcursos a implementar. |
| **9. Desempenho e 16. Relatórios** | **Ausente** | Indicadores reais dependentes das tabelas de sessões, revisões e questões. |
| **10. Jurisprudência e 11. Súmulas** | **Ausente** | Cadastro rastreável com fonte e data de verificação a implementar. |
| **12. Editais e PDFs / 13. Banco de Conteúdos** | **Parcial (apenas em CSV/XLSX estático)** | O inventário CSV/XLSX já cataloga os arquivos locais com hash SHA-256, mas falta a interface e persistência no banco da aplicação. |
| **14. Nivelamento e 15. Radar** | **Ausente** | Diagnóstico inicial por assunto e acompanhamento manual de concursos a implementar. |
| **17. Configurações e Backup/Restauração** | **Ausente** | Parametrização de disponibilidade, limites diários, intervalos e exportação do banco a implementar. |

---

## 4. Divergências, Riscos e Pontos de Atenção Identificados

1. **Divergência de caminhos históricos em alguns registros do CSV vs. localização física atual:**
   - Alguns relatórios e linhas antigas do `INVENTARIO_GERAL_CONCURSO_2027.csv` fazem referência a subcaminhos da antiga árvore `01_DOCUMENTOS/...`, enquanto os arquivos físicos estão todos armazenados diretamente nas **6 pastas principais da raiz** (`01_EDITAIS_E_PLANEJAMENTO` a `06_MATERIAIS_E_INVENTARIO`).
   - **Mitigação na Fase 2/7:** O indexador/leitor do Banco de Conteúdos da aplicação deverá resolver o arquivo pelo nome e hash SHA-256 dentro das 6 pastas oficiais sem mover nem alterar os arquivos originais e sem sobrescrever o CSV original sem autorização.
2. **Arquivos sinalizados na auditoria do acervo (duplicados, inválidos ou com nome trocado):**
   - Conforme documentado em `RELATORIO_AUDITORIA_QUALIDADE_ACERVO_2027.md`, existem no disco arquivos mantidos por regra de preservação que são duplicados (ex.: `Resolucao_CD_ANPD_18_2024_Encarregado_DPO.pdf`), shells HTML SPA de 114 caracteres (`SERPRO_2023_Cebraspe_Oficial.html`, `TCU_2025_AUFC_TI_Cebraspe.html`), um download inválido (`Lei_PE_19159_2025_..._download_invalido.html`) ou arquivo com título interno diferente do nome em disco (`ANPD_Guia_Poder_Publico.pdf`, que contém o Guia de Cookies Out/2022).
   - **Mitigação:** A plataforma deve preservar todos os arquivos intocados no disco e exibir no módulo **Banco de Conteúdos** exatamente a classificação de utilidade e os alertas auditados no inventário.
3. **Política de execução de scripts PowerShell (`ExecutionPolicy`):**
   - No ambiente Windows atual, scripts `.ps1` (como `npm.ps1`) são bloqueados por padrão.
   - **Mitigação:** Utilizar `npm.cmd` ou executar scripts via `node` / `python` diretamente.
4. **Isolamento do código da aplicação em relação às 6 pastas do acervo:**
   - Para respeitar a Seção 7 da Especificação (*"As seis pastas principais do acervo são acervo documental, não módulos da aplicação. Não recriar pastas antigas"*), a Fase 2 deverá definir onde o código-fonte da aplicação e o arquivo de banco de dados residirão dentro da raiz oficial (por exemplo, em uma estrutura limpa como `app/` ou `src/` + `data/` na raiz, sem tocar nas 6 pastas numeradas).

---

## 5. Conclusão do Diagnóstico (Critério de Aceite da Fase 1)

O diagnóstico técnico foi concluído com base estrita nos 221 arquivos efetivamente encontrados na raiz oficial `C:\Users\nadja\OneDrive\Documents\2027 PLATAFORMA`. Não há código legado com dívida técnica ou dependências quebradas, e o ambiente local dispõe de **Node.js v24.22.0** (com `node:sqlite` nativo) e **Python 3.13.5** (com `sqlite3` nativo), permitindo projetar na **Fase 2** uma arquitetura local robusta, rápida, com persistência SQLite real e zero dependência de serviços pagos ou externos.
