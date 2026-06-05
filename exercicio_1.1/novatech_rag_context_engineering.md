# Análise Técnica de Context Engineering e RAG — NovaTech

> **Escopo**: Análise para o assistente de IA da equipe de atendimento ao cliente da NovaTech, cobrindo desafios de pipeline por tipo de fonte, estimativa de base em tokens, orçamento de contexto por modelo e estratégias de chunking orientadas ao conceito de *Lost in the Middle*.

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
| Indexação estruturada como fallback | Azure SQL + Text-to-SQL (Semantic Kernel) | Para tabelas de lookup puras, indexar como banco de dados relacional e usar Text-to-SQL como estratégia paralela ao RAG vetorial |
| Extração de fluxogramas | Azure AI Vision / GPT-4o Vision | Gerar descrição textual de cada diagrama embutido e indexá-la como chunk adicional com metadado `tipo: fluxograma` |

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
| Detecção automática de PDFs escaneados | Heurística de cobertura textual | Se menos de 10% das páginas do PDF contêm texto nativo extraível, acionar automaticamente o pipeline de OCR |
| Normalização pós-OCR | Dicionário de termos do domínio (logística) | Mapear erros comuns: `"praz0"` → `"prazo"`, `"frele"` → `"frete"`, `"Kg."` → `"kg"`. Manter log de substituições para auditoria |
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
| Resolução de links internos (1 nível de profundidade) | Spider/crawler custom sobre a API do Confluence | Ao indexar uma página, incluir os primeiros 200 tokens das páginas linkadas como contexto adicional, suficiente para fornecer referência sem sobrecarregar o índice |
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

- LLMs não conseguem interpretar fórmulas Excel como valores → respostas contendo `"=VLOOKUP(...)"` no lugar de valores concretos, inutilizando a resposta para o atendente.
- Perguntas sobre cálculo de frete retornam respostas genéricas ou matematicamente incorretas por falta dos valores calculados corretos.
- Interdependências entre abas não capturadas resultam em respostas parciais onde parâmetros-chave do cálculo estão ausentes.

#### Estratégia de Tratamento

| Ação | Ferramenta Recomendada | Detalhe Técnico |
|---|---|---|
| Extração de valores calculados (não fórmulas) | `openpyxl` com `data_only=True` ou `pandas` | Abrir arquivo Excel após recálculo automático; capturar apenas os valores finais das células, nunca as fórmulas |
| Serialização contextual linha a linha | Pós-processamento custom (Python) | Cada linha vira um documento de texto: `"Tipo Cliente: Gold | Região: SE | SLA: 48h | Frete_min: R$X | Frete_max: R$Y"` |
| Resolução de dependências entre abas | Processamento integrado do arquivo .xlsx completo | Processar todas as abas antes de serializar; resolver referências cruzadas entre abas na etapa de extração, não na indexação |
| Indexação estruturada como estratégia paralela | Azure SQL Database + Text-to-SQL | Para planilhas com estrutura tabular clara e queries de lookup frequentes, indexar como tabela SQL para consultas determinísticas |
| Reindexação incremental mensal | Pipeline com hash SHA-256 do arquivo | Detectar mudanças comparando o hash do arquivo atual com o da versão indexada; reindexar apenas os arquivos que sofreram alteração |

---

## Seção 2 — Estimativa da Base de Dados em Tokens

### Base dos Cálculos

**Regra utilizada (fornecida no briefing):** 1 token ≈ 0,75 palavras

**Fórmula de conversão:**
```
Tokens = Palavras ÷ 0,75
```

**Premissas por tipo de documento:**

> ⚠️ **Nota de transparência**: A estimativa de palavras por página para PDFs e por arquivo de planilha não foi especificada no briefing. Os valores abaixo são estimativas técnicas baseadas em padrões de mercado para documentos corporativos de logística. Em caso de divergência com a realidade do cliente, solicitar uma amostra representativa para calibrar os valores antes do início da indexação.

- **PDFs**: Média de **300 palavras/página** — estimativa conservadora para documentos técnico-comerciais com conteúdo misto (texto corrido + tabelas). Páginas com tabelas densas terão menos palavras; páginas com texto corrido, mais.
- **Wiki Confluence**: **1.500 palavras/página** — fornecido pelo cliente.
- **Planilhas**: Estimativa de **3.000 palavras/arquivo** após serialização contextual — baseada em planilha com ~100 linhas × 15 colunas, com média de 2 palavras por célula serializada (cabeçalho + valor).

---

### Cálculos Passo a Passo (Chain-of-Thought)

**Passo 1 — PDFs:**
```
Número de páginas = 800 documentos × 10 páginas/doc
                  = 8.000 páginas

Total de palavras = 8.000 páginas × 300 palavras/pág
                  = 2.400.000 palavras

Total de tokens   = 2.400.000 ÷ 0,75
                  = 3.200.000 tokens
```

**Passo 2 — Wiki Confluence:**
```
Total de palavras = 400 páginas × 1.500 palavras/pág
                  = 600.000 palavras

Total de tokens   = 600.000 ÷ 0,75
                  = 800.000 tokens
```

**Passo 3 — Planilhas:**
```
Total de palavras = 50 arquivos × 3.000 palavras/arq
                  = 150.000 palavras

Total de tokens   = 150.000 ÷ 0,75
                  = 200.000 tokens
```

**Passo 4 — Total geral:**
```
Total de palavras = 2.400.000 + 600.000 + 150.000
                  = 3.150.000 palavras

Total de tokens   = 3.200.000 + 800.000 + 200.000
                  = 4.200.000 tokens
```

**Passo 5 — Percentuais:**
```
% PDFs       = 3.200.000 ÷ 4.200.000 × 100 = 76,19% ≈ 76,2%
% Wiki       = 800.000   ÷ 4.200.000 × 100 = 19,05% ≈ 19,0%
% Planilhas  = 200.000   ÷ 4.200.000 × 100 =  4,76% ≈  4,8%

Verificação  = 76,2% + 19,0% + 4,8%        = 100,0% ✓
```

---

### Tabela de Estimativa da Base

| Tipo de Documento | Quantidade | Palavras/Unidade | Total de Palavras | Total de Tokens | % da Base Total |
|---|---|---|---|---|---|
| PDFs (tabelas, fluxogramas e escaneados) | 800 docs × 10 pág. = **8.000 páginas** | 300 palavras/pág.¹ | 2.400.000 | **3.200.000** | **76,2%** |
| Wiki Confluence | **400 páginas** | 1.500 palavras/pág. | 600.000 | **800.000** | **19,0%** |
| Planilhas (.xlsx) | **50 arquivos** | ~3.000 palavras/arq.² | 150.000 | **200.000** | **4,8%** |
| **TOTAL** | — | — | **3.150.000** | **4.200.000** | **100,0%** |

> ¹ Premissa do autor: média conservadora para documentos de logística com mix de texto e tabelas.
> ² Premissa do autor: baseada em planilha com ~100 linhas × 15 colunas serializada com contexto de cabeçalho.

**Conclusão crítica:** Os ~4,2 milhões de tokens da base total **não cabem em nenhuma janela de contexto de modelos disponíveis comercialmente hoje**. Isso confirma tecnicamente que o RAG é a arquitetura correta para o projeto — em vez de enviar o corpus inteiro ao LLM, o sistema deve recuperar apenas os chunks relevantes para cada query em tempo real.

---

## Seção 3 — Análise de Orçamento de Contexto

### Base dos Cálculos

Para calcular quantos chunks de ~500 tokens cabem por query, adota-se a seguinte decomposição do orçamento de tokens da janela de contexto:

```
╔══════════════════════════════════════════════════════════════╗
║              DECOMPOSIÇÃO DO ORÇAMENTO DE CONTEXTO           ║
╠══════════════════════════════════════════════════════════════╣
║  System prompt + instruções:  ~2.000 tokens  (fornecido)     ║
║  Query do usuário:              ~200 tokens  (estimativa)    ║
║  Buffer de resposta gerada:   ~2.000 tokens  (estimativa)    ║
╠══════════════════════════════════════════════════════════════╣
║  OVERHEAD TOTAL = 4.200 tokens                               ║
║  DISPONÍVEL PARA CHUNKS = Janela Total − 4.200 tokens        ║
║  Nº DE CHUNKS = Disponível ÷ 500 tokens/chunk                ║
╚══════════════════════════════════════════════════════════════╝
```

**Cálculos detalhados por modelo (Chain-of-Thought):**

```
GPT-4o (128K):
  Disponível para chunks = 128.000 − 4.200 = 123.800 tokens
  Nº de chunks           = 123.800 ÷ 500   = 247,6 → ~247 chunks (teórico)

GPT-4o mini (128K):
  Disponível para chunks = 128.000 − 4.200 = 123.800 tokens
  Nº de chunks           = 123.800 ÷ 500   = 247,6 → ~247 chunks (teórico)

Claude 3.5 Sonnet / Claude Sonnet 4 (200K):
  Disponível para chunks = 200.000 − 4.200 = 195.800 tokens
  Nº de chunks           = 195.800 ÷ 500   = 391,6 → ~391 chunks (teórico)

Gemini 1.5 Pro (1M):
  Disponível para chunks = 1.000.000 − 4.200 = 995.800 tokens
  Nº de chunks           = 995.800   ÷ 500   = 1.991,6 → ~1.991 chunks (teórico)
```

> ⚠️ **Nota crítica — Lost in the Middle**: Os números teóricos acima raramente devem ser atingidos na prática. Pesquisas demonstram que LLMs prestam significativamente mais atenção ao **início** e ao **final** do contexto, com recall reduzindo para informações posicionadas no meio de contextos longos — o chamado efeito *"Lost in the Middle"* (Liu et al., 2023). O número **prático recomendado** é de **5 a 15 chunks por query**, independentemente do tamanho da janela do modelo.

---

### Tabela de Orçamento de Contexto

| Modelo de IA | Tamanho da Janela de Contexto | Chunks de ~500 Tokens por Query (teórico) | Como Isso Afeta a Estratégia de Chunking e Retrieval |
|---|---|---|---|
| **GPT-4o** | 128.000 tokens | **(128.000 − 4.200) ÷ 500 ≈ 247 chunks** | Janela generosa, mas o efeito *lost in the middle* é severo acima de ~15 chunks. Estratégia: usar **top-k = 5 a 10** com re-ranking por cross-encoder (ex.: Cohere Rerank). Posicionar os chunks mais relevantes **no início e no fim** do contexto para máxima atenção. Modelo recomendado para NovaTech via Azure AI Services. |
| **GPT-4o mini** | 128.000 tokens | **(128.000 − 4.200) ÷ 500 ≈ 247 chunks** | Mesma janela teórica do GPT-4o, mas com menor capacidade de raciocínio em contextos longos. Recomendado **k ≤ 8** e chunks menores (~300 tokens) para maior precisão. Adequado para queries simples de lookup com baixo custo; não recomendado para síntese de múltiplas fontes. |
| **Claude 3.5 Sonnet / Claude Sonnet 4** | 200.000 tokens | **(200.000 − 4.200) ÷ 500 ≈ 391 chunks** | Modelos Claude são treinados para maior recall em posições intermediárias do contexto, atenuando o *lost in the middle*. Ainda assim, manter **k ≤ 15**. Janela maior é útil para recuperar múltiplos documentos relacionados sem cortar contexto. Considerar para casos que exijam síntese de muitas fontes simultâneas. |
| **Gemini 1.5 Pro** | 1.000.000 tokens | **(1.000.000 − 4.200) ÷ 500 ≈ 1.991 chunks** | Janela extremamente grande permite ingestão de corpus inteiro teoricamente, mas a atenção dilui severamente com contextos muito longos. Custo por query muito elevado. Adequado somente para análise batch com sumarização em camadas (map-reduce). **Não recomendado** para atendimento em tempo real da NovaTech. |

---

## Seção 4 — Estratégia de Chunking por Tipo de Pergunta

> **Premissa de design**: Toda estratégia de chunking abaixo leva em conta o efeito *Lost in the Middle*. O princípio central é: **quanto menos chunks no contexto, melhor o recall** — portanto, a seletividade do retrieval (filtros de metadados + re-ranking) é tão importante quanto o chunking em si. Os chunks mais relevantes devem sempre ser posicionados no **início** do contexto ao montar o prompt final.

---

### Tabela de Estratégias de Chunking

| Possível Tipo de Pergunta do Usuário | Estratégia de Chunking | Justificativa pelo Tipo de Pergunta e Conceito do Lost in the Middle |
|---|---|---|
| **Lookup pontual** — *"Qual o prazo de entrega para cliente Gold na região Sul?"* | Chunks **pequenos (~200–300 tokens) por linha de tabela serializada**, com metadados ricos (`tipo_cliente`, `regiao`, `tipo_carga`) para filtragem pré-retrieval | A pergunta busca um valor específico em uma tabela. Chunks pequenos aumentam a precisão do embedding e reduzem ruído semântico. Com filtros de metadados aplicados antes da busca vetorial, o retrieval entrega 1–3 chunks de alta relevância — eliminando o *lost in the middle* por manter o contexto curto e focado em apenas o dado buscado. |
| **Pergunta de política/regra** — *"Quais são os critérios para abertura de reclamação de avaria?"* | Chunks **médios (~400–500 tokens) por seção semântica** (delimitados por H2/H3), sempre incluindo o título da seção e o breadcrumb da fonte no início do chunk | A resposta exige um parágrafo completo de política; cortar no meio invalida o sentido da regra. O breadcrumb no início (`[Políticas > Reclamações > Avaria]`) ancora o LLM semanticamente e evita confusão quando múltiplos chunks de políticas diferentes são recuperados. Posicionar o chunk mais relevante **no início do contexto** para máxima atenção. |
| **Pergunta procedimental** — *"Quais são os passos para processar uma devolução?"* | Chunks **sequenciais por etapa de processo (~300–400 tokens)**, com metadado de ordem (`step_order: 1, 2, 3...`) | Processos têm ordem lógica obrigatória; cortar no meio de uma etapa gera resposta incompleta. O metadado de sequência permite montar os chunks em ordem correta no contexto: **etapa 1 no início** e **etapa final no fim** do prompt — aproveitando que LLMs prestam mais atenção a essas posições e evitando que etapas críticas caiam no "meio morto" do contexto. |
| **Pergunta comparativa** — *"Qual a diferença entre SLA Tipo A e SLA Tipo B?"* | Chunks **médios (~400–500 tokens) com agrupamento forçado** — os dois objetos de comparação devem coexistir no contexto, preferencialmente posicionados próximos entre si | Comparações exigem que ambos os objetos sejam visíveis ao LLM simultaneamente. Se os dois chunks ficarem no meio de um contexto longo e extenso, o *lost in the middle* compromete a qualidade da comparação. Estratégia: recuperar os dois chunks e posicioná-los **no início do contexto**, seguidos de no máximo 3 chunks complementares ao final. |
| **Pergunta de cálculo** — *"Como calcular o frete para 500 kg de carga refrigerada?"* | **Par vinculado de chunks**: chunk de tabela serializada (~400–600 tokens) + chunk da regra de cálculo associada (~300 tokens), recuperados juntos via metadado de grupo (`doc_grupo: calculo_frete`) | O LLM precisa do valor da tabela E da regra de cálculo juntos para dar uma resposta correta. Separar em chunks distantes no contexto aumenta o risco de um deles cair no "meio morto" e ser ignorado. Limitar a 4–5 chunks no total para garantir atenção máxima em ambos os documentos-âncora. Posicionar tabela primeiro, regra logo após. |
| **Pergunta de conflito/versão** — *"Meu cliente diz que recebeu uma informação diferente — qual é a regra atual para frete expresso?"* | Chunks com **metadados de versão e data** (`data_publicacao`, `versao`), com retrieval priorizando o documento mais recente via filtro de data antes da busca vetorial | Contradições entre versões são um problema identificado na NovaTech. Metadados de data permitem filtrar e priorizar a versão mais recente antes mesmo de calcular similaridade vetorial. O chunk da versão vigente deve ser posicionado no **início do contexto** (maior atenção); versões anteriores, se incluídas como referência, devem ser indicadas como "versão anterior" e posicionadas ao final. |
| **Pergunta aberta/orientação** — *"O que devo fazer quando um cliente reclama de atraso na entrega?"* | **Hierarquia de chunks**: sumário do processo (~200 tokens) posicionado no início + detalhes de cada etapa (~400 tokens × 3) posicionados ao final; aplicar **HyDE** (Hypothetical Document Embedding) para melhorar o retrieval inicial | Perguntas abertas exigem síntese de múltiplas fontes e têm vocabulário diferente dos documentos de procedimento. HyDE gera uma resposta hipotética que melhora a qualidade semântica da busca vetorial. No contexto final: **sumário do processo no início** para ancorar o LLM + detalhes das etapas ao final — evitando deliberadamente o "meio morto" para os chunks críticos. Limitar a 8 chunks no total. |

---

*Documento elaborado para uso interno — Projeto NovaTech × DB1 | Análise de Context Engineering e RAG*
