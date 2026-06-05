# Análise Técnica de Context Engineering e RAG — NovaTech

> **Escopo**: Análise para o assistente de IA da equipe de atendimento ao cliente da NovaTech, cobrindo desafios de pipeline por tipo de fonte, estimativa de base em tokens, orçamento de contexto por modelo e estratégias de chunking orientadas ao conceito de *Lost in the Middle*.
>
> **Revisão v2 — Alterações desta versão:**
> - Correção da regra de tokenização para português (0,62 palavras/token em vez de 0,75)
> - Adição de overhead de serialização contextual no cálculo de tokens de planilhas
> - Correção do orçamento de contexto: remoção do "buffer de resposta" do budget de input; adição de histórico de conversa ao overhead; aumento do sistema de prompt para estimativa enterprise realista
> - Correção de bug técnico crítico: `openpyxl data_only=True` não recalcula fórmulas
> - Refinamento da detecção de PDFs escaneados de nível de documento para nível de página
> - Correção da estratégia de resolução de links internos no Confluence
> - Adição de sobreposição (*overlap*) entre chunks como prática padrão
> - Adição de caveats para afirmações não comprovadas sobre Lost in the Middle e Claude
> - Nova Seção 5 — Riscos Operacionais e Considerações Adicionais

---

## Seção 1 — Análise por Tipo de Fonte de Dados

---

### 1.1 PDFs com Tabelas Complexas

#### Desafio para o Pipeline de RAG

Tabelas com 15+ colunas representam um dos maiores desafios para pipelines de RAG convencionais. Os problemas estruturais são:

- **Fragmentação de contexto relacional**: Estratégias de chunking por tamanho fixo cortam linhas de tabela separando valores de seus respectivos cabeçalhos. Uma célula com `"R$ 48,00"` perde completamente seu significado sem saber que pertence à coluna `"Frete/kg"` e à linha `"Cliente Premium — Região Sul"`.
- **Cabeçalhos não replicados**: Os cabeçalhos de coluna aparecem apenas uma vez no topo da tabela. Chunks subsequentes ficam sem a referência de qual coluna pertence cada valor, tornando a leitura ambígua.
- **Fluxogramas embutidos como imagem**: Diagramas de processo embutidos são completamente ignorados por extratores de texto convencionais (PyMuPDF, pdfplumber), gerando lacunas invisíveis no índice — o atendente pergunta sobre um fluxo e o RAG simplesmente não tem o conteúdo.
- **Serialização plana**: Extratores de texto convertem tabelas em linhas sequenciais de texto, destruindo o alinhamento coluna-valor que define o significado dos dados.

#### Impacto na Qualidade das Respostas

O LLM recebe fragmentos de linhas sem contexto de coluna, resultando em:

- **Alucinação de lookup**: perguntas do tipo *"Qual o prazo para cliente Tipo B na região Norte?"* podem retornar valores de outra combinação de linha/coluna adjacente no chunk.
- Alta taxa de erro em perguntas numéricas onde precisão é crítica (SLAs, tarifas, prazos contratuais).
- Respostas parciais com lacunas onde os fluxogramas estariam.

#### Estratégia de Tratamento

| Ação | Ferramenta Recomendada | Detalhe Técnico |
|---|---|---|
| Extração com reconhecimento de layout | Azure AI Document Intelligence (Layout API) | Preserva estrutura de tabela; retorna JSON com linhas, colunas e células mapeadas com coordenadas |
| Serialização contextual por linha | Pós-processamento custom (Python) | Converter cada linha em texto autoexplicativo: `"Tipo Cliente: Premium | Região: Sul | Frete/kg: R$X | SLA: 24h"` |
| Chunking semântico por tabela | Chunk = cabeçalhos + grupo de linhas relacionadas | Replicar cabeçalhos em todo chunk de tabela; nunca cortar uma linha no meio |
| Indexação estruturada como estratégia paralela | Azure SQL + Text-to-SQL (Semantic Kernel) | ⚠️ **Esforço de sub-projeto independente**: Text-to-SQL exige schema discovery, prompt engineering específico, validação de queries geradas e tratamento de erros semânticos. Para tabelas de lookup puras e queries de alta frequência, o ganho de determinismo justifica o custo; dimensionar como iniciativa paralela, não como fallback trivial |
| Extração de fluxogramas | Azure AI Vision / GPT-4o Vision | Gerar descrição textual de cada diagrama embutido e indexá-la como chunk adicional com metadado `tipo: fluxograma`. Executar na etapa de ingestão, não em tempo real de query |

---

### 1.2 PDFs Escaneados (OCR Necessário)

#### Desafio para o Pipeline de RAG

- **Texto ausente nativamente**: Extratores convencionais de PDF retornam strings vazias em documentos escaneados; o texto precisa ser gerado via OCR antes de qualquer etapa do pipeline.
- **Erros de OCR corrompem embeddings**: A string `"praz0 de entrega: 48h"` tem um embedding vetorial diferente de `"prazo de entrega: 48h"`, reduzindo drasticamente o recall no retrieval por similaridade. O chunk correto existe no índice, mas não é recuperado porque seu embedding diverge da query.
- **Qualidade variável por documento**: Documentos antigos ou de baixa resolução produzem erros de caractere que corrompem valores críticos como preços (`"R$12,50"` → `"R$12.5O"`), datas e códigos de produto.
- **Estrutura destruída**: Tabelas e listas formatadas visualmente são frequentemente linearizadas incorretamente pelo OCR, gerando blocos de texto sem estrutura semântica.
- **Metadados ausentes**: Documentos escaneados raramente possuem metadados nativos (data, autor, versão), dificultando o controle de versão e a priorização temporal no retrieval.

#### Impacto na Qualidade das Respostas

- Erros de OCR introduzem ruído nos embeddings que degrada o recall; o chunk correto pode não ser recuperado mesmo sendo semanticamente relevante.
- Valores numéricos incorretos (datas, preços, prazos) são passados diretamente ao LLM, que os utiliza sem questionar — gerando respostas com dados errados servidos com confiança.
- Estrutura destruída resulta em chunks incoerentes que o LLM não consegue interpretar corretamente, forçando a geração de respostas genéricas.

#### Estratégia de Tratamento

| Ação | Ferramenta Recomendada | Detalhe Técnico |
|---|---|---|
| OCR com reconhecimento de layout | Azure AI Document Intelligence (Read API) | Alta acurácia para português, preserva estrutura de tabela, retorna coordenadas de cada elemento da página |
| Detecção de páginas escaneadas por página individual | Heurística de cobertura textual **por página** | ⚠️ **Correção de abordagem**: a detecção deve ser feita por página, não por documento. Verificar o número de caracteres extraíveis via `pdftotext` em cada página individualmente; páginas com menos de 50 caracteres são tratadas como escaneadas e enviadas ao pipeline de OCR, independentemente do restante do documento. Documentos híbridos — com partes textuais e partes escaneadas — são comuns em arquivos corporativos legados e requerem tratamento misto |
| Normalização pós-OCR | Dicionário de termos do domínio (logística) | Mapear erros comuns: `"praz0"` → `"prazo"`, `"frele"` → `"frete"`, `"Kg."` → `"kg"`. Manter log de substituições para auditoria. Considerar dicionário vivo com revisão mensal pela equipe de documentação |
| Score de confiança como metadado | Confidence score do Azure Document Intelligence | Chunks com confiança < 80% recebem flag `baixa_confianca: true` no metadado; o assistente sinaliza ao atendente que deve verificar a fonte original |
| Revisão humana de documentos críticos | Processo operacional | Documentos de compliance e SLA originalmente escaneados devem passar por revisão manual antes da indexação para garantir integridade |

---

### 1.3 Wiki Confluence com Links Internos e Macros

#### Desafio para o Pipeline de RAG

- **Referências quebradas**: Uma página wiki pode conter `"veja os prazos na [Tabela de SLA]"` com hyperlink para outra página; ao ser indexada isoladamente, o chunk perde o conteúdo referenciado, tornando a resposta incompleta por design.
- **Macros não renderizadas**: Macros do Confluence (`{status}`, `{jira-issues}`, painéis dinâmicos) são exportadas como markup bruto (`{panel:title=Atenção|borderColor=red}`) sem valor semântico, gerando ruído nos embeddings e reduzindo a qualidade do retrieval.
- **Hierarquia perdida**: O contexto de uma página filha depende do contexto da página pai. *"Procedimento de Exceção de Devolução"* é subpágina de *"Manual do Atendente > Devoluções"*; sem essa hierarquia, o chunk fica sem âncora semântica e o LLM não sabe a qual área operacional ele pertence.
- **Conteúdo dinâmico desatualizado**: Macros que exibem dados em tempo real (status de sistemas, queries Jira) ficam inúteis quando exportadas como snapshot estático, podendo induzir o LLM a usar informações desatualizadas.

#### Impacto na Qualidade das Respostas

- Respostas incompletas porque o conteúdo referenciado por links não está no contexto do LLM.
- Fragmentos com macros não renderizadas geram ruído nos embeddings, reduzindo a precisão do retrieval e trazendo chunks irrelevantes ao contexto.
- Sem hierarquia, o LLM não consegue determinar a qual processo ou área o chunk pertence, aumentando a chance de respostas fora de contexto.

#### Estratégia de Tratamento

| Ação | Ferramenta Recomendada | Detalhe Técnico |
|---|---|---|
| Exportação via API com renderização completa | Confluence REST API (`/rest/api/content/{id}?expand=body.view`) | Obter o HTML renderizado com macros expandidas, não o storage format cru. Macros renderizadas viram conteúdo textual real |
| Indexação completa de páginas linkadas | Confluence API + crawler de grafo de links | ⚠️ **Correção de abordagem**: páginas referenciadas por links internos devem ser indexadas como chunks completos e independentes no índice vetorial — não como prefixo fixo de 200 tokens. O conteúdo relevante raramente está nos primeiros 200 tokens de uma página; truncar introduz informação incompleta e descarta a parte potencialmente útil. Os links são preservados como metadado de relacionamento (`linked_from: [id_pagina_origem]`), permitindo filtragem e ranqueamento durante o retrieval |
| Metadados de hierarquia (breadcrumb) | Confluence API: campo `page.ancestors` | Adicionar breadcrumb ao início de cada chunk: `[Manual Atendente > Devoluções > Procedimento de Exceção]`. Serve como âncora contextual para o LLM |
| Chunking por seção semântica | Delimitação por H1/H2/H3 da página | Respeitar a estrutura de cabeçalhos da wiki; nunca quebrar uma seção semântica no meio de um parágrafo |
| Remoção de macros não resolvidas | Pós-processamento com regex + whitelist | Remover blocos `{macro...}` que não geraram conteúdo útil após renderização; logar para revisão pela equipe de documentação |

---

### 1.4 Planilhas com Fórmulas Interdependentes

#### Desafio para o Pipeline de RAG

- **Fórmulas ≠ Valores**: A extração de texto de uma planilha no modo padrão captura a fórmula bruta (`=VLOOKUP(A2,TabelaFrete,3,0)`) em vez do valor calculado, tornando o chunk completamente ininterpretável para o LLM.
- **Dependências entre abas**: Uma planilha de cálculo de frete pode depender de uma aba *"Parâmetros"* e outra *"Regiões"*; extraídas isoladamente, as abas perdem o contexto que as conecta e os valores ficam descontextualizados.
- **Contexto de célula perdido**: O valor `"48"` em uma célula isolada não diz nada; o contexto completo é `"Coluna: SLA_Horas | Linha: Cliente_Gold | Região: Sudeste | Valor: 48"`.
- **Reindexação mensal crítica**: As planilhas são atualizadas mensalmente por áreas diferentes; sem detecção de mudanças, o RAG pode servir dados de meses anteriores com confiança indevida.

#### Impacto na Qualidade das Respostas

- LLMs não conseguem interpretar fórmulas Excel como valores → respostas contendo `"=VLOOKUP(...)"`  no lugar de valores concretos, inutilizando a resposta para o atendente.
- Perguntas sobre cálculo de frete retornam respostas genéricas ou matematicamente incorretas por falta dos valores calculados corretos.
- Interdependências entre abas não capturadas resultam em respostas parciais onde parâmetros-chave do cálculo estão ausentes.

#### Estratégia de Tratamento

| Ação | Ferramenta Recomendada | Detalhe Técnico |
|---|---|---|
| Extração de valores calculados (não fórmulas) | `openpyxl` com `data_only=True` — **com ressalva crítica** | ⚠️ **Bug amplamente documentado**: `data_only=True` lê apenas valores em cache salvos pela última abertura do arquivo no Microsoft Excel. Se as planilhas forem geradas ou modificadas por scripts Python, automações ou qualquer ferramenta que não seja o Excel nativo, o cache não existe — `openpyxl` retorna `None` para todas as células com fórmula, silenciosamente e sem erro. **Alternativas**: (1) Converter o arquivo via LibreOffice headless antes da extração (`soffice --headless --calc --convert-to xlsx`), que força recálculo; (2) Usar `xlwings` em ambiente Windows com Excel instalado; (3) Exigir que o processo operacional salve os arquivos com valores fixados (sem fórmulas) antes da ingestão |
| Serialização contextual linha a linha | Pós-processamento custom (Python) | Cada linha vira um documento de texto: `"Tipo Cliente: Gold | Região: SE | SLA: 48h | Frete_min: R$X | Frete_max: R$Y"`. Ver nota sobre overhead de tokens na Seção 2 |
| Resolução de dependências entre abas | Processamento integrado do arquivo .xlsx completo | Processar todas as abas antes de serializar; resolver referências cruzadas entre abas na etapa de extração, não na indexação |
| Indexação estruturada como estratégia paralela | Azure SQL Database + Text-to-SQL | Para planilhas com estrutura tabular clara e queries de lookup frequentes, indexar como tabela SQL para consultas determinísticas. Ver nota de esforço na Seção 1.1 |
| Reindexação incremental mensal | Pipeline com hash SHA-256 do arquivo | Detectar mudanças comparando o hash do arquivo atual com o da versão indexada; reindexar apenas os arquivos que sofreram alteração |

---

## Seção 2 — Estimativa da Base de Dados em Tokens

### Base dos Cálculos

**Regra de tokenização para português:**

> ⚠️ **Correção da versão anterior**: A regra `1 token ≈ 0,75 palavras` é calibrada para inglês, com base no tokenizador BPE treinado majoritariamente em corpora anglófonos. Para português, a morfologia mais rica (conjugações verbais, sufixos de gênero/número, palavras compostas) gera tokens em média mais longos. A relação empírica para português com tokenizadores da família GPT e Claude é de aproximadamente **1 token ≈ 0,60–0,65 palavras**. Esta análise adota **0,62 palavras/token** como estimativa conservadora central.

**Fórmula de conversão (corrigida):**
```
Tokens = Palavras ÷ 0,62
```

**Premissas por tipo de documento:**

> ⚠️ **Nota de transparência**: As estimativas de palavras por página para PDFs e por arquivo de planilha não foram especificadas no briefing. Os valores abaixo são estimativas técnicas baseadas em padrões de mercado para documentos corporativos de logística. Em caso de divergência com a realidade do cliente, solicitar uma amostra representativa de 20 documentos para calibrar os valores antes do início da indexação.

- **PDFs**: Média de **300 palavras/página** — estimativa conservadora para documentos técnico-comerciais com conteúdo misto (texto corrido + tabelas). Páginas com tabelas densas terão menos palavras; páginas com texto corrido, mais.
- **Wiki Confluence**: **1.500 palavras/página** — fornecido pelo cliente.
- **Planilhas**: Estimativa de **3.000 palavras/arquivo** como base de conteúdo bruto — planilha com ~100 linhas × 15 colunas, com média de 2 palavras por célula. **Após serialização contextual**, cada linha recebe prefixo de cabeçalho replicado (`"Col1: val | Col2: val | ... | Col15: val"`), o que adiciona aproximadamente 60% de tokens extras sobre o conteúdo bruto. A estimativa efetiva é **3.000 × 1,60 = 4.800 palavras efetivas/arquivo**.

---

### Cálculos Passo a Passo (Chain-of-Thought)

**Passo 1 — PDFs:**
```
Número de páginas = 800 documentos × 10 páginas/doc
                  = 8.000 páginas

Total de palavras = 8.000 páginas × 300 palavras/pág
                  = 2.400.000 palavras

Total de tokens   = 2.400.000 ÷ 0,62
                  = 3.870.968 ≈ 3.871.000 tokens
```

**Passo 2 — Wiki Confluence:**
```
Total de palavras = 400 páginas × 1.500 palavras/pág
                  = 600.000 palavras

Total de tokens   = 600.000 ÷ 0,62
                  = 967.742 ≈ 968.000 tokens
```

**Passo 3 — Planilhas:**
```
Palavras base          = 50 arquivos × 3.000 palavras/arq
                       = 150.000 palavras

Overhead serialização  = 150.000 × 1,60 (fator de overhead contextual)
                       = 240.000 palavras efetivas

Total de tokens        = 240.000 ÷ 0,62
                       = 387.097 ≈ 387.000 tokens
```

**Passo 4 — Total geral:**
```
Total de palavras efetivas = 2.400.000 + 600.000 + 240.000
                           = 3.240.000 palavras efetivas

Total de tokens            = 3.871.000 + 968.000 + 387.000
                           = 5.226.000 tokens
```

**Passo 5 — Percentuais:**
```
% PDFs      = 3.871.000 ÷ 5.226.000 × 100 = 74,1%
% Wiki      = 968.000   ÷ 5.226.000 × 100 = 18,5%
% Planilhas = 387.000   ÷ 5.226.000 × 100 =  7,4%

Verificação = 74,1% + 18,5% + 7,4%        = 100,0% ✓
```

---

### Tabela de Estimativa da Base

| Tipo de Documento | Quantidade | Palavras Brutas/Unidade | Total de Palavras Brutas | Fator Ajuste | Palavras Efetivas | Total de Tokens | % da Base Total |
|---|---|---|---|---|---|---|---|
| PDFs (tabelas, fluxogramas e escaneados) | 800 docs × 10 pág. = **8.000 páginas** | 300 palavras/pág.¹ | 2.400.000 | — | 2.400.000 | **3.871.000** | **74,1%** |
| Wiki Confluence | **400 páginas** | 1.500 palavras/pág. | 600.000 | — | 600.000 | **968.000** | **18,5%** |
| Planilhas (.xlsx) | **50 arquivos** | ~3.000 palavras/arq.² | 150.000 | ×1,60³ | 240.000 | **387.000** | **7,4%** |
| **TOTAL** | — | — | **3.150.000** | — | **3.240.000** | **5.226.000** | **100,0%** |

> ¹ Premissa do autor: média conservadora para documentos de logística com mix de texto e tabelas. Calibrar com amostra real antes do início da ingestão.
> ² Premissa do autor: baseada em planilha com ~100 linhas × 15 colunas com contexto de cabeçalho.
> ³ Fator de overhead de serialização contextual: cabeçalhos replicados por linha aumentam o volume efetivo de tokens em ~60% sobre o conteúdo bruto.

> ⚠️ **Comparativo com versão anterior**: A versão v1 desta análise estimava ~4,2M tokens usando a regra de tokenização para inglês e sem overhead de serialização. A estimativa corrigida para português com overhead de serialização é de **~5,2M tokens** — aproximadamente 24% superior. A conclusão principal permanece inalterada: a base total não cabe em nenhuma janela de contexto disponível comercialmente, confirmando RAG como a arquitetura correta.

---

## Seção 3 — Análise de Orçamento de Contexto

### Base dos Cálculos

Para calcular quantos chunks de ~500 tokens cabem por query, adota-se a seguinte decomposição do orçamento de tokens da janela de contexto:

```
╔══════════════════════════════════════════════════════════════════════╗
║         DECOMPOSIÇÃO DO ORÇAMENTO DE CONTEXTO (CORRIGIDO)           ║
╠══════════════════════════════════════════════════════════════════════╣
║  System prompt + instruções:  ~3.500 tokens  (ver nota ²)            ║
║  Query do usuário:              ~200 tokens  (estimativa)             ║
║  Histórico de conversa:       ~0–6.000 tokens (variável — ver nota ³) ║
╠══════════════════════════════════════════════════════════════════════╣
║  OVERHEAD BASE (sem histórico)       ≈ 3.700 tokens                  ║
║  OVERHEAD COM HISTÓRICO (5 turnos)   ≈ 9.700 tokens                  ║
║  DISPONÍVEL PARA CHUNKS = Janela de Input Total − Overhead           ║
║  Nº DE CHUNKS = Disponível ÷ 500 tokens/chunk                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  ¹ Tokens de output (resposta gerada) possuem orçamento SEPARADO e  ║
║    NÃO são subtraídos da janela de input nos modelos desta análise.  ║
╚══════════════════════════════════════════════════════════════════════╝
```

> ¹ **Tokens de output — orçamento separado (correção da v1):** Para GPT-4o, Claude Sonnet e Gemini 1.5 Pro, os tokens de output são cobrados e gerenciados em orçamento distinto do input. O parâmetro `max_tokens` (ou `max_completion_tokens`) controla o limite de geração sem consumir a janela de input. A versão anterior desta análise subtraía 2.000 tokens de "buffer de resposta" da janela de input, o que era conceitualmente incorreto para esses modelos e gerava cálculo de chunks disponíveis levemente subestimado.

> ² **System prompt enterprise:** Um system prompt bem elaborado para RAG de atendimento corporativo tipicamente inclui: contexto da empresa e persona do assistente, instruções detalhadas de citação de fonte (com exemplos), tratamento de informações contraditórias, formato de resposta, comportamento quando informação não é encontrada, restrições de domínio e exemplos few-shot. O total realista é de **3.000 a 6.000 tokens**. Esta análise adota 3.500 tokens como estimativa conservadora. A versão anterior usava 2.000 tokens, valor subestimado para esse tipo de aplicação.

> ³ **Histórico de conversa:** Em uma interface de chat com histórico, cada turno anterior é adicionado ao contexto. Para uma conversa de 5 turnos com respostas médias de ~600 tokens por turno, o histórico acumula ~6.000 tokens adicionais ao overhead, reduzindo o espaço disponível para chunks e podendo empurrar o `k` prático para 5–8 em vez de 10–15 para modelos com janelas menores.

**Cálculos detalhados por modelo (Chain-of-Thought), dois cenários:**

```
─────────────────────────────────────────────────────────────
GPT-4o
  Janela de input:  128.000 tokens
  Output:           até 16.384 tokens (orçamento separado)

  Cenário A — Sem histórico de conversa:
    Disponível para chunks = 128.000 − 3.700 = 124.300 tokens
    Nº de chunks           = 124.300 ÷ 500   = 248,6 → ~248 chunks (teórico)

  Cenário B — 5 turnos de histórico:
    Disponível para chunks = 128.000 − 9.700 = 118.300 tokens
    Nº de chunks           = 118.300 ÷ 500   = 236,6 → ~236 chunks (teórico)

─────────────────────────────────────────────────────────────
GPT-4o mini
  Janela de input:  128.000 tokens
  Output:           até 16.384 tokens (orçamento separado)

  Cenário A:  ~248 chunks (idêntico ao GPT-4o)
  Cenário B:  ~236 chunks

─────────────────────────────────────────────────────────────
Claude Sonnet 4
  Janela de input:  200.000 tokens
  Output:           até 8.192 tokens (orçamento separado)

  Cenário A — Sem histórico:
    Disponível para chunks = 200.000 − 3.700 = 196.300 tokens
    Nº de chunks           = 196.300 ÷ 500   = 392,6 → ~392 chunks (teórico)

  Cenário B — 5 turnos de histórico:
    Disponível para chunks = 200.000 − 9.700 = 190.300 tokens
    Nº de chunks           = 190.300 ÷ 500   = 380,6 → ~380 chunks (teórico)

─────────────────────────────────────────────────────────────
Gemini 1.5 Pro
  Janela de input:  1.000.000 tokens
  Output:           até 8.192 tokens (orçamento separado)

  Cenário A — Sem histórico:
    Disponível para chunks = 1.000.000 − 3.700 = 996.300 tokens
    Nº de chunks           = 996.300   ÷ 500   = 1.992,6 → ~1.992 chunks (teórico)

  Cenário B — 5 turnos de histórico:
    Disponível para chunks = 1.000.000 − 9.700 = 990.300 tokens
    Nº de chunks           = 990.300   ÷ 500   = 1.980,6 → ~1.980 chunks (teórico)
─────────────────────────────────────────────────────────────
```

> ⚠️ **Nota crítica — Lost in the Middle**: Os números teóricos acima raramente devem ser atingidos na prática. Pesquisas demonstram que LLMs prestam significativamente mais atenção ao **início** e ao **final** do contexto, com recall reduzindo para informações posicionadas no meio de contextos longos — o chamado efeito *"Lost in the Middle"* (Liu et al., 2023). O número **prático recomendado** é de **5 a 15 chunks por query**, independentemente do tamanho da janela do modelo. O cenário B (com histórico) reforça essa recomendação: a redução de espaço disponível para chunks é secundária ao efeito de atenção.

---

### Tabela de Orçamento de Contexto

| Modelo de IA | Janela de Input | Output (orçamento separado) | Chunks de ~500 tokens — Cenário A (sem histórico) | Chunks de ~500 tokens — Cenário B (5 turnos) | Como Isso Afeta a Estratégia |
|---|---|---|---|---|---|
| **GPT-4o** | 128.000 tokens | até 16.384 tokens | **(128.000 − 3.700) ÷ 500 ≈ 248 chunks** | **(128.000 − 9.700) ÷ 500 ≈ 236 chunks** | Janela generosa, mas o efeito *lost in the middle* é severo acima de ~15 chunks. Estratégia: usar **top-k = 5 a 10** com re-ranking por cross-encoder (ex.: Cohere Rerank). Posicionar os chunks mais relevantes **no início e no fim** do contexto para máxima atenção. Modelo recomendado para NovaTech via Azure AI Services. |
| **GPT-4o mini** | 128.000 tokens | até 16.384 tokens | **≈ 248 chunks** | **≈ 236 chunks** | Mesma janela teórica do GPT-4o, mas com menor capacidade de raciocínio em contextos longos e maior suscetibilidade a alucinação com informações contraditórias. Recomendado **k ≤ 8** e chunks menores (~300 tokens) para maior precisão. Adequado para queries simples de lookup com baixo custo; **não** recomendado para síntese de múltiplas fontes ou documentos contraditórios. |
| **Claude Sonnet 4** | 200.000 tokens | até 8.192 tokens | **(200.000 − 3.700) ÷ 500 ≈ 392 chunks** | **(200.000 − 9.700) ÷ 500 ≈ 380 chunks** | Janela maior é útil para recuperar múltiplos documentos relacionados sem cortar contexto. Manter **k ≤ 15** — a recomendação independe do modelo. ⚠️ Afirmações de que modelos Claude "atenuam" o Lost in the Middle em contextos longos não são sustentadas por benchmark público conclusivo; adotar a mesma cautela de posicionamento que nos demais modelos. |
| **Gemini 1.5 Pro** | 1.000.000 tokens | até 8.192 tokens | **(1.000.000 − 3.700) ÷ 500 ≈ 1.992 chunks** | **(1.000.000 − 9.700) ÷ 500 ≈ 1.980 chunks** | Janela extremamente grande permite ingestão de corpus inteiro teoricamente, mas a atenção dilui severamente com contextos muito longos. Custo por query muito elevado. Adequado somente para análise batch com sumarização em camadas (map-reduce). **Não recomendado** para atendimento em tempo real da NovaTech. |

---

## Seção 4 — Estratégia de Chunking por Tipo de Pergunta

> **Premissa de design**: Toda estratégia de chunking abaixo leva em conta o efeito *Lost in the Middle*. O princípio central é: **quanto menos chunks no contexto, melhor o recall** — portanto, a seletividade do retrieval (filtros de metadados + re-ranking) é tão importante quanto o chunking em si. Os chunks mais relevantes devem sempre ser posicionados no **início** do contexto ao montar o prompt final.

> **Overlap entre chunks:** Todos os chunks de texto corrido devem ser criados com sobreposição (*overlap*) de **15–20%** em relação ao chunk adjacente — por exemplo, 75–100 tokens de overlap para chunks de 500 tokens. O overlap evita a perda de contexto nas bordas: regras, cláusulas ou etapas que começam no final do chunk N e terminam no chunk N+1 não ficam semanticamente truncadas em nenhum dos dois. **Exceção**: chunks de linhas de tabela serializadas **não** recebem overlap, pois cada linha é semanticamente autocontida e o overlap duplicaria dados de forma inútil.

---

### Tabela de Estratégias de Chunking

| Possível Tipo de Pergunta do Usuário | Estratégia de Chunking | Justificativa pelo Tipo de Pergunta e Conceito do Lost in the Middle |
|---|---|---|
| **Lookup pontual** — *"Qual o prazo de entrega para cliente Gold na região Sul?"* | Chunks **pequenos (~200–300 tokens) por linha de tabela serializada**, com metadados ricos (`tipo_cliente`, `regiao`, `tipo_carga`) para filtragem pré-retrieval. **Sem overlap** entre linhas. | A pergunta busca um valor específico em uma tabela. Chunks pequenos aumentam a precisão do embedding e reduzem ruído semântico. Com filtros de metadados aplicados antes da busca vetorial, o retrieval entrega 1–3 chunks de alta relevância — eliminando o *lost in the middle* por manter o contexto curto e focado em apenas o dado buscado. |
| **Pergunta de política/regra** — *"Quais são os critérios para abertura de reclamação de avaria?"* | Chunks **médios (~400–500 tokens) por seção semântica** (delimitados por H2/H3), com **overlap de 75–100 tokens** entre seções adjacentes, e título da seção + breadcrumb no início do chunk. | A resposta exige um parágrafo completo de política; cortar no meio invalida o sentido da regra. O breadcrumb (`[Políticas > Reclamações > Avaria]`) ancora o LLM semanticamente. O overlap garante que regras que atravessam a fronteira entre seções sejam capturadas por pelo menos um dos chunks. Posicionar o chunk mais relevante **no início do contexto**. |
| **Pergunta procedimental** — *"Quais são os passos para processar uma devolução?"* | Chunks **sequenciais por etapa de processo (~300–400 tokens)**, com **overlap de 60–80 tokens** entre etapas e metadado de ordem (`step_order: 1, 2, 3...`). Atribuição de `step_order` via parsing de marcadores de lista numerada (H3 com número, `1.`, `Passo 1:`) na etapa de ingestão. | Processos têm ordem lógica obrigatória. O metadado de sequência permite montar os chunks em ordem correta: **etapa 1 no início** e **etapa final no fim** do prompt. O overlap garante que a transição entre etapas não perca instruções de handoff. |
| **Pergunta comparativa** — *"Qual a diferença entre SLA Tipo A e SLA Tipo B?"* | Chunks **médios (~400–500 tokens) com agrupamento forçado** — os dois objetos de comparação devem coexistir no contexto, posicionados próximos entre si e preferencialmente no início. | Comparações exigem que ambos os objetos sejam visíveis ao LLM simultaneamente. Estratégia: recuperar os dois chunks e posicioná-los **no início do contexto**, seguidos de no máximo 3 chunks complementares ao final — evitando que um dos termos da comparação caia no "meio morto". |
| **Pergunta de cálculo** — *"Como calcular o frete para 500 kg de carga refrigerada?"* | **Par vinculado de chunks**: chunk de tabela serializada (~400–600 tokens, sem overlap) + chunk da regra de cálculo associada (~300 tokens, com overlap em relação a chunks de regra adjacentes), recuperados juntos via metadado de grupo (`doc_grupo: calculo_frete`). | O LLM precisa do valor da tabela E da regra de cálculo juntos para dar uma resposta correta. Limitar a 4–5 chunks no total. Posicionar tabela primeiro, regra logo após — ambos no início do contexto. |
| **Pergunta de conflito/versão** — *"Meu cliente diz que recebeu uma informação diferente — qual é a regra atual para frete expresso?"* | Chunks com **metadados de versão e data** (`data_publicacao`, `versao`), com retrieval priorizando o documento mais recente via filtro de data **antes** da busca vetorial. **Atenção:** ver nota de confiabilidade de metadados na Seção 5.4. | Contradições entre versões são um problema identificado na NovaTech. Metadados de data permitem filtrar e priorizar a versão mais recente antes mesmo de calcular similaridade vetorial. O chunk da versão vigente deve ser posicionado no **início do contexto**; versões anteriores, se incluídas como referência, devem ser indicadas como "versão anterior" e posicionadas ao final. |
| **Pergunta aberta/orientação** — *"O que devo fazer quando um cliente reclama de atraso na entrega?"* | **Hierarquia de chunks com overlap**: sumário do processo (~200 tokens) no início + detalhes de cada etapa (~400 tokens × 3, com overlap de 80 tokens entre etapas) ao final. Aplicar **HyDE** (Hypothetical Document Embedding) para melhorar o retrieval inicial — com atenção ao custo operacional. | Perguntas abertas exigem síntese de múltiplas fontes e têm vocabulário diferente dos documentos de procedimento. HyDE gera uma resposta hipotética que melhora a qualidade semântica da busca vetorial. ⚠️ HyDE requer uma chamada LLM adicional por query, adicionando ~1–3 segundos de latência e custo equivalente a ~6.000 chamadas extras/mês no volume da NovaTech — aplicar apenas para esse tipo de query complexa, não globalmente. Limitar a 8 chunks no total. |

---

## Seção 5 — Riscos Operacionais e Considerações Adicionais

---

### 5.1 Prazo de 3 Meses — Risco Alto

O escopo técnico descrito nesta análise acumula no mínimo seis pipelines de ingestão distintos (PDFs nativos com tabelas via Document Intelligence, PDFs escaneados com OCR, fluxogramas via Vision API, Confluence com spider de links e remoção de macros, planilhas com serialização e resolução de dependências entre abas, e Text-to-SQL como estratégia paralela), além de reranking com cross-encoder, HyDE para queries abertas, controle de versão por hash e metadados de confiança de OCR.

**Recomendação**: Definir um MVP explícito para o go-live de 3 meses — por exemplo, cobertura apenas de PDFs nativos e wiki Confluence, sem Text-to-SQL e sem HyDE — com roadmap documentado para as demais fontes. Implementar todo o escopo descrito com qualidade de produção em 3 meses é tecnicamente viável apenas com equipe dedicada de 4+ engenheiros. Apresentar esse trade-off à diretoria antes do início do desenvolvimento.

---

### 5.2 Estratégia de Avaliação — Ausente na v1

Nenhuma análise RAG enterprise está completa sem definir como medir se o sistema funciona. Sem métricas de avaliação, não é possível iterar com evidência nem demonstrar para a diretoria que a meta de 12→2 minutos foi atingida.

**Métricas recomendadas:**

- **Retrieval**: Precision@k e Recall@k — dos chunks recuperados, quantos são de fato relevantes? Das fontes relevantes para a query, quantas foram recuperadas?
- **Faithfulness (fidelidade)**: a resposta gerada é sustentada pelos chunks no contexto, ou o LLM está alucinando informação não presente?
- **Answer Relevance**: a resposta endereça diretamente a pergunta do atendente?
- **Latência end-to-end**: tempo médio da query até a resposta exibida na interface. Meta de negócio: reduzir de 12 min para menos de 2 min não é apenas sobre a latência do LLM — inclui o tempo do atendente para reformular a query e avaliar a resposta.
- **Frameworks sugeridos**: RAGAS (open-source), TruLens, ou avaliação manual periódica com amostra de 50 queries reais por sprint.

**Processo recomendado**: montar um conjunto de avaliação (*eval set*) de 100–200 pares de query-resposta-fonte esperada antes do início do desenvolvimento, com participação da equipe de atendimento na validação. Esse conjunto é o critério de aceite técnico do projeto.

---

### 5.3 Modelo de Embedding para Português — Ausente na v1

A seleção do modelo de embedding é tão crítica quanto a estratégia de chunking e está completamente ausente da análise. Usar o modelo padrão sem considerar o idioma pode degradar o recall em 15–30% em benchmarks de recuperação para português.

**Comparação relevante:**

| Modelo | Multilingual | Performance Português | Observação |
|---|---|---|---|
| `text-embedding-ada-002` | Parcial | Abaixo do ideal | Treinado majoritariamente em inglês; recall inferior para português técnico |
| `text-embedding-3-large` | Parcial | Razoável | Melhor que ada-002, mas ainda com gap vs. modelos multilinguais dedicados |
| `multilingual-e5-large` | Sim | Alta | Open-source; disponível via Azure ML ou HuggingFace |
| `azure-text-embedding` (Cohere Embed Multilingual) | Sim | Alta | Disponível via Azure AI Services; boa performance para texto corporativo |

**Recomendação**: Avaliar `multilingual-e5-large` ou Cohere Embed Multilingual com uma amostra do corpus real antes de fixar a escolha. O modelo de embedding deve ser incluído no eval set da Seção 5.2.

---

### 5.4 Contradições Documentais e Confiabilidade de Metadados de Versão

O cenário explicitamente menciona que documentos se contradizem entre versões e que não existe processo unificado de revisão. A análise propõe metadados de `data_publicacao` e `versao` para priorizar a versão mais recente — mas essa solução tem uma dependência crítica não abordada: **os metadados precisam existir de forma confiável nos documentos originais**.

Um PDF escaneado de 2019 sem data legível e uma versão Word de 2023 sem campo de versão preenchido tornam o filtro por data inoperante — o sistema pode servir a versão desatualizada com aparência de confiança. Isso é potencialmente pior do que a situação atual, onde o atendente ao menos sabe que deve "perguntar para quem sabe".

**Recomendações complementares:**

1. Conduzir, antes da ingestão, um inventário de metadados disponíveis nos documentos reais das três fontes.
2. Definir um processo operacional de enriquecimento de metadados para os documentos que não possuem data/versão confiável — mesmo que manual para o acervo histórico.
3. Quando o sistema não puder determinar a versão mais recente com confiança, a resposta deve explicitar a incerteza ao atendente ("Encontrei duas versões deste procedimento com datas distintas — recomendo validar com a área de Compliance antes de utilizar").
4. Endereçar o problema raiz com as três áreas (Operações, Compliance, Comercial): sem processo unificado de publicação e versionamento, o assistente pode amplificar a inconsistência em vez de resolvê-la.

---

### 5.5 Controle de Acesso — Ausente na v1

A análise não menciona permissões de documentos. O SharePoint corporativo provavelmente possui ACLs (Access Control Lists) — documentos de RH, compliance regulatório ou termos comerciais específicos podem não ser acessíveis a todos os 45 atendentes.

**Riscos:**
- Um assistente RAG sem controle de acesso pode surfaçar para um atendente informações restritas contidas em documentos a que ele não teria acesso na fonte original.
- Violações de LGPD se documentos com dados pessoais (ex.: histórico de clientes, termos individuais) forem indexados sem controle de leitura.

**Recomendações**: Mapear ACLs do SharePoint e do Confluence antes da indexação; implementar filtragem por perfil de acesso no retrieval (o Azure AI Search suporta filtros por metadados de permissão); excluir explicitamente da indexação documentos com classificação de dados sensíveis que não se apliquem ao perfil do atendente de atendimento geral.

---

*Documento elaborado para uso interno — Projeto NovaTech × DB1 | Análise de Context Engineering e RAG | Versão 2*
