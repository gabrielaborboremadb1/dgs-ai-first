# Análise dos Resultados

---

## Pergunta 1 — "Qual o prazo de devolução?"

**Status:** ⚠️ Não foi satisfatório

### Gabarito (Anexo B)

- **Devem ser recuperados:** POL-001-A (Prazo geral), POL-001-B (Exceções)
- **Podem aparecer:** POL-001-C (Procedimento)

### Chunks recuperados pelo pipeline

| #   | Chunk ID                  | Documento       | Seção                                                                                        | Score  | Correto?                                                                    |
| --- | ------------------------- | --------------- | -------------------------------------------------------------------------------------------- | ------ | --------------------------------------------------------------------------- |
| 1   | POL-001_chunk_005         | POL-001         | 3.4. Devoluções parciais e 3.5. Custos de devolução                                          | 0.8059 | ❌ Comenta de devolução, mas não fala de prazo                              |
| 2   | POL-001_chunk_004         | POL-001         | 3.3. Procedimento de devolução                                                               | 0.7770 | ✅ Chunk relacionado, retornado corretamente                                |
| 3   | FAQ-Atendimento_chunk_001 | FAQ-Atendimento | Perguntas selecionadas (Item 3 e Item 8)                                                     | 0.7544 | ❌ Fala sobre devolução de carga perigosa                                   |
| 4   | POL-001_chunk_001         | POL-001         | 3. Regras de Devolução (Prazo geral)                                                         | 0.7439 | ✅ Equivalente ao POL-001-A do gabarito, porém trouxe o cabeçalho "3" junto |
| 5   | FAQ-Atendimento_chunk_005 | FAQ-Atendimento | Item 41 — SLA resposta vs resolução e Item 45 — O cliente quer desconto no frete. Posso dar? | 0.7343 | ❌ Não comenta nada sobre devolução nem prazo                               |

### Análise

- O pipeline recuperou o documento correto (POL-001) com 1 chunk correto e 1 chunk relacionado.
- O pipeline não recuperou corretamente o POL-001-B (Seção 3.2. Exceções ao prazo geral)
- O Score dos chunks menos relevantes (FAQ-03 e FAQ-08) foram maiores, enquanto do chunk mais relevante POL-001-A foi menor
- Chunks do FAQ e de devoluções parciais são ruído, mas não impediram a resposta correta.
- A resposta do teste no Claude foi suficiente, porém com riscos

---

## Pergunta 2 — "Posso devolver carga perigosa?"

**Status:** ⚠️ Não foi satisfatório

### Gabarito (Anexo B)

- **Devem ser recuperados:** POL-001-B (Exceções — cargas perigosas NÃO elegíveis)
- **Podem aparecer:** FAQ-03, POL-001-A

### Chunks recuperados pelo pipeline

| #   | Chunk ID                  | Documento       | Seção                                  | Score  | Correto?                                                                        |
| --- | ------------------------- | --------------- | -------------------------------------- | ------ | ------------------------------------------------------------------------------- |
| 1   | FAQ-Atendimento_chunk_004 | FAQ-Atendimento | Item 38 — Carga danificada em trânsito | 0.7736 | ❌ Trata de carga danificada, não devolução de carga perigosa                   |
| 2   | POL-001_chunk_005         | POL-001         | 3.4. Devoluções parciais               | 0.7426 | ⚠️ Fala dos custos de devolução, mas não fala especificamente de carga perigosa |
| 3   | FAQ-Atendimento_chunk_002 | FAQ-Atendimento | Item 15 — Tier Platinum                | 0.7421 | ❌ Irrelevante                                                                  |
| 4   | PROC-042_chunk_002        | PROC-042        | 3. Prazo de entrega frete especial     | 0.7416 | ❌ Irrelevante                                                                  |
| 5   | FAQ-Atendimento_chunk_001 | FAQ-Atendimento | Perguntas selecionadas (Item 3)        | 0.7384 | ✅ Equivalente ao FAQ-03 — menciona carga perigosa e ramal 4500                 |

### Análise

- O pipeline trouxe conteúdo sem relacionamento com carga perigosa do FAQ (carga danificada e tier platinum).
- O chunk POL-001-B (seção 3.2 — "NÃO são elegíveis") não apareceu no top-5.
- O score dos chunks mais relevantes foram os menores.
- A fonte formal/autoritativa ficou ausente.
- Isso é um risco: o LLM pode basear a resposta no FAQ (fonte informal) em vez da política oficial.
- Apesar diso a resposta do teste no Claude foi suficiente, porém com riscos pois a informação veio do FAQ

---

## Pergunta 3 — "Qual o SLA do cliente Gold?"

**Status:** ✅ Satisfatório

### Gabarito (Anexo B)

- **Devem ser recuperados:** SLA-2024-B (Tabela de SLAs — chamados gerais)
- **Podem aparecer:** SLA-2024-A (Classificação), SLA-2024-C (Incidentes críticos)

### Chunks recuperados pelo pipeline

| #   | Chunk ID                  | Documento       | Seção                               | Score  | Correto?                                          |
| --- | ------------------------- | --------------- | ----------------------------------- | ------ | ------------------------------------------------- |
| 1   | SLA-2024_chunk_004        | SLA-2024        | 4. Penalidades por descumprimento   | 0.8080 | ⚠️ Menciona penalidades por descumprimento do SLA |
| 2   | SLA-2024_chunk_001        | SLA-2024        | 1. Classificação de clientes        | 0.7892 | ✅ Equivalente ao SLA-2024-A do gabarito          |
| 3   | FAQ-Atendimento_chunk_005 | FAQ-Atendimento | Item 41 — SLA resposta vs resolução | 0.7771 | ⚠️ Relacionado mas não é fonte formal             |
| 4   | SLA-2024_chunk_002        | SLA-2024        | 2. Tabela de SLAs                   | 0.7469 | ✅ Equivalente ao SLA-2024-B do gabarito          |
| 5   | SLA-2024_chunk_000        | SLA-2024        | Cabeçalho do documento              | 0.7468 | ⚠️ Metadata do doc, pouca informação útil         |

### Análise

- Retorno maioria das informações formais relevantes e complementares do FAQ.
- Não retornou o chunk SLA-2024-C que poderia aparecer no gabarito.
- No geral a pipeline se comportou de maneira satisfatória.
- Score bem parelho e adequado.
- Claude respondeu corretamente seguindo guardrails e citando fontes

---

## Pergunta 4 — "Qual o SLA do cliente Platinum?"

**Status:** ✅ Satisfatório

### Gabarito (Anexo B)

- **Devem ser recuperados:** SLA-2024-A (contém "não existem outros tiers")
- **Podem aparecer:** FAQ-15 (Tier Platinum não existe)

### Chunks recuperados pelo pipeline

| #   | Chunk ID                  | Documento       | Seção                                | Score  | Correto?                                         |
| --- | ------------------------- | --------------- | ------------------------------------ | ------ | ------------------------------------------------ |
| 1   | SLA-2024_chunk_001        | SLA-2024        | 1. Classificação de clientes         | 0.7756 | ✅ Equivalente ao SLA-2024-A                     |
| 2   | SLA-2024_chunk_000        | SLA-2024        | Cabeçalho do documento               | 0.7645 | ⚠️ Metadata, pouca info útil                     |
| 3   | FAQ-Atendimento_chunk_002 | FAQ-Atendimento | Item 15 — "Não existe tier Platinum" | 0.7611 | ✅ Equivalente ao FAQ-15                         |
| 4   | SLA-2024_chunk_004        | SLA-2024        | 4. Penalidades                       | 0.7596 | ⚠️ Complementar                                  |
| 5   | SLA-2024_chunk_002        | SLA-2024        | 2. Tabela de SLAs                    | 0.7582 | ⚠️ Complementar — ajuda a mostrar os tiers reais |

### Análise

- O pipeline recuperou exatamente os chunks necessários para que o LLM diga que "Platinum não existe".
- Chunk 1 (SLA-2024-A) diz que só existem 3 tiers; chunk 3 (FAQ-15) reforça que Platinum não existe.
- O score foi bem parelho e satisfatório.
- Informações não relacionadas a pergunta não geram tanto ruído, são complementares.
- Claude respondeu corretamente seguindo guardrails e citando fontes

---

## Pergunta 5 — "Frete para 600kg para Manaus?"

**Status:** ⚠️ Parcial

### Gabarito (Anexo B)

- **Devem ser recuperados:** PROC-042v2-B (Multiplicadores atualizados), PROC-042v2-A (Fórmula atualizada)
- **Podem aparecer:** PROC-042-B (versão antiga — risco de contradição)

### Chunks recuperados pelo pipeline

| #   | Chunk ID              | Documento     | Seção                              | Score  | Correto?                                                   |
| --- | --------------------- | ------------- | ---------------------------------- | ------ | ---------------------------------------------------------- |
| 1   | PROC-042_chunk_002    | PROC-042 (v1) | 3. Prazo de entrega frete especial | 0.7355 | ⚠️ Versão antiga — risco de contradição                    |
| 2   | PROC-042-v2_chunk_001 | PROC-042-v2   | 2. Fórmula de cálculo              | 0.7238 | ✅ Equivalente ao PROC-042v2-A (fórmula + multiplicadores) |
| 3   | PROC-042_chunk_001    | PROC-042 (v1) | 1. Objetivo + Fórmula              | 0.7225 | ⚠️ Versão antiga — risco de contradição                    |
| 4   | PROC-042_chunk_000    | PROC-042 (v1) | Cabeçalho                          | 0.7188 | ⚠️ Versão antiga                                           |
| 5   | PROC-042-v2_chunk_000 | PROC-042-v2   | 1. Objetivo                        | 0.7173 | ✅ Doc correto, seção introdutória                         |

### Análise

- **Problema crítico identificado:** 3 dos 5 chunks são da versão antiga (PROC-042 v1).
  - v1: Norte = 1.6 | v2: Norte = 1.8
- A versão desatualizada (v1) teve score maior, o que pode fazer o assistente dar informações incorretas.
- O LLM precisa usar as disposições transitórias (PROC-042v2-E) para decidir qual versão aplicar, mas esse chunk não foi recuperado.
- Informações complementares como as seções 3 e 4 vieram do documento antigo (v1).
- O sistema prompt instrui a priorizar documentos mais recentes, o que mitiga parcialmente o risco.
- Claude respondeu corretamente, porém devido a instrução do system prompt. Pode ter riscos

---

## Pergunta 6 — "Qual o multiplicador de frete para o Sudeste?"

**Status:** ❌ Falha

### Gabarito (Anexo B)

- **Devem ser recuperados:** PROC-042v2-B (Multiplicadores atualizados — Sudeste = 1.1)
- **Podem aparecer:** PROC-042-B (versão antiga — contradição: 1.0 vs 1.1)

### Chunks recuperados pelo pipeline

| #   | Chunk ID                  | Documento       | Seção                           | Score  | Correto?                                           |
| --- | ------------------------- | --------------- | ------------------------------- | ------ | -------------------------------------------------- |
| 1   | FAQ-Atendimento_chunk_001 | FAQ-Atendimento | Perguntas selecionadas (Item 3) | 0.7489 | ❌ Irrelevante — trata de devolução                |
| 2   | POL-001_chunk_005         | POL-001         | 3.4. Devoluções parciais        | 0.7344 | ❌ Irrelevante                                     |
| 3   | PROC-042_chunk_001        | PROC-042 (v1)   | 1. Objetivo + Fórmula           | 0.7217 | ⚠️ Doc parcialmente correto mas versão errada (v1) |
| 4   | POL-001_chunk_004         | POL-001         | 3.3. Procedimento de devolução  | 0.7200 | ❌ Irrelevante                                     |
| 5   | FAQ-Atendimento_chunk_000 | FAQ-Atendimento | Cabeçalho FAQ                   | 0.7195 | ❌ Irrelevante                                     |

### Análise

- **Falha total de retrieval.** Nenhum chunk do PROC-042-v2 foi recuperado no top-5.
- O chunk da tabela do v1 foi retornado, trazendo informações desatualizadas.
- **Causa raiz:** O modelo de embedding (`all-MiniLM-L6-v2`) é treinado em inglês e não correlaciona adequadamente "multiplicador para o Sudeste" com o conteúdo tabular dos multiplicadores regionais em português.
- Scores muito baixos (0.72–0.75) indicam que nenhum chunk tem alta similaridade semântica com a query.
- O FAQ apareceu no topo porque tem termos genéricos que o modelo confunde semanticamente.
- **Crítico:** O Claude responde incorretamente com com confiança **alta**.

---

## Resumo Geral

| #   | Pergunta                        | Status          | Docs Esperados   | Docs Recuperados       | Score Máx | Observação                                                                                                        |
| --- | ------------------------------- | --------------- | ---------------- | ---------------------- | --------- | ----------------------------------------------------------------------------------------------------------------- |
| 1   | Qual o prazo de devolução?      | ⚠️ Parcial      | POL-001          | POL-001, FAQ           | 0.8059    | Trouxe informações suficientes pra responder, mas maioria dos chunks devolvidos não foram ideais                  |
| 2   | Posso devolver carga perigosa?  | ⚠️ Parcial      | POL-001          | POL-001, FAQ, PROC-042 | 0.7736    | Fonte formal ausente do top-5                                                                                     |
| 3   | Qual o SLA do cliente Gold?     | ✅ Satisfatório | SLA-2024         | SLA-2024, FAQ          | 0.8080    | Excelente cobertura, poderia ter acrescentado o chunk sobre incidentes ao invés de outros menos relevantes        |
| 4   | Qual o SLA do cliente Platinum? | ✅ Satisfatório | SLA-2024, FAQ-15 | SLA-2024, FAQ          | 0.7756    | Detectou bem a falta do tier platinum                                                                             |
| 5   | Frete para 600kg para Manaus?   | ⚠️ Parcial      | PROC-042-v2      | PROC-042-v2, PROC-042  | 0.7355    | Risco de contradição v1 vs v2                                                                                     |
| 6   | Multiplicador frete Sudeste?    | ❌ Falha        | PROC-042-v2      | FAQ, POL-001, PROC-042 | 0.7489    | Falha total — embedding não correlaciona query com tabela. Assistente respondeu incorretamente com confiança alta |

**Taxa de acerto:** 3.5/6 (58.33%)

---

## Problemas Identificados

1. **Modelo de embedding anglófono:** O `all-MiniLM-L6-v2` tem dificuldade com termos técnicos em português, especialmente quando a query usa palavras diferentes das que
   aparecem no documento (ex: "multiplicador para o Sudeste" vs tabela com "Sudeste 1.1").

2. **Contradição entre versões:** Na pergunta 5, chunks de ambas as versões do PROC-042 foram recuperados simultaneamente, criando risco de o LLM misturar dados
   obsoletos com atuais. Inclusive priorizando documentos da v1, quando deveriam ser priorizados documentos da v2.

3. **Chunks do FAQ como ruído:** Em 5 das 6 perguntas, chunks do FAQ-Atendimento apareceram sem necessidade. O FAQ usa linguagem informal que cria falsa similaridade semântica
   com muitas queries.

4. **Ranking não ideal:** Na pergunta 1 e 2, chunks mais relevantes ficaram abaixo dos chunks menos relevantes.

5. **Cabeçalhos Irrelevantes:** Nas perguntas 3, 4, 5 e 6 Cabeçalho do documento é retornado quando muitas vezes quando não é necessário.

6. **Não traz todos documentos relevantes:** Nas perguntas 1 e 2, informações formais ou complementares que seriam relevantes não foram trazidas. Ao invés disso foram trazidos
   cabeçalhos e chunks irrelevantes

7. **Faixa de scores muito estreita:** Tanto chunks relevantes quanto irrelevantes caem na mesma faixa de score.Na pergunta 6 (falha total), os chunks irrelevantes têm
   score 0.72–0.75 — quase igual aos "bons" da pergunta 3 (0.75–0.81). O MIN_RELEVANCE_SCORE=0.65 nunca filtra nada porque todos os resultados ficam acima. Isso é sintoma do
   modelo anglófono produzindo embeddings "genéricos" para texto em português.

8. **Prefixo de contextualização do chunk pode diluir a especificidade do embedding:** Cada chunk é armazenado com prefixo [DOC_ID] Título — Seção, o que faz chunks do mesmo
   documento terem embeddings mais parecidos entre si do que deveriam. Isso explica por que cabeçalhos e seções irrelevantes do mesmo doc aparecem juntos
   (ex: na pergunta 3, o cabeçalho do SLA-2024 aparece com score quase igual ao da tabela real).

## Soluções Propostas:

1. Trocar modelo de embedding para multilíngue (multilingual-e5-large ou paraphrase-multilingual-MiniLM-L12-v2)

2. Filtro de metadados por versão: Na busca, quando existem v1 e v2 do mesmo procedimento, filtrar por version mais recente ou boostar score de docs mais novos

3. Reduzir CHUNK_SIZE para 500-600 chars para chunks mais específicos por subseção, evitando que uma seção 3.4 entre junto com 3.5

4. Excluir cabeçalhos/metadata do chunking: Filtrar o bloco YAML/metadata do topo do documento antes do split, ou criar chunk separado de metadata que não entra no retrieval

5. Ponderar source_type no score final: Dar boost a chunks de documentos normativo vs FAQ quando a query é sobre regras/políticas

6. Aumentar DEFAULT_TOP_K para 8-10 e filtrar após reranking: Recuperar mais candidatos e aplicar um cross-encoder reranker (ex: cross-encoder/ms-marco-MiniLM-L-6-v2) para reordenar com mais precisão

7. Query expansion: Antes da busca, expandir a query com sinônimos/termos técnicos (ex: "multiplicador Sudeste" → "multiplicador regional Sudeste tabela frete") via prompt ao LLM ou regras simples

8. Remover prefixo do texto embedado e manter apenas no texto exibido no prompt. Armazenar separadamente: embedding do chunk puro + texto com contexto para exibição
