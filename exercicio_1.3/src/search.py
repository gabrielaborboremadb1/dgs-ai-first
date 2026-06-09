"""
Módulo de Busca — NovaTech RAG PoC

Recebe uma pergunta em texto natural, gera o embedding da query,
busca os top-k chunks mais similares no ChromaDB, e retorna os
resultados com score de similaridade e metadados.

Melhorias implementadas:
- Filtro/boost por versão: quando existem v1 e v2 do mesmo procedimento,
  a versão mais recente recebe boost de score (+0.05) e a antiga penalidade (-0.05)
- Query expansion: expande a query com sinônimos/termos técnicos antes da busca
- Ponderação por source_type: docs normativos recebem boost vs FAQ/informais

Regras de retrieval (definidas no system prompt v2):
- Máximo: 5 chunks por query
- Descartar chunks com score < 0.65
- Ordenação para injeção no prompt: maior score PRIMEIRO,
  segundo maior POR ÚLTIMO, demais no meio (mitiga lost-in-the-middle)
"""

import re
from dataclasses import dataclass

import chromadb
from config import (CHROMA_DB_DIR, COLLECTION_NAME, DEFAULT_TOP_K,
                    EMBEDDING_MODEL, MIN_RELEVANCE_SCORE, RETRIEVAL_CANDIDATES)
from sentence_transformers import SentenceTransformer


@dataclass
class SearchResult:
    """Resultado de busca de um chunk."""

    chunk_id: str
    text: str
    score: float  # Similaridade coseno (0-1, maior = mais similar)
    metadata: dict


def load_search_components():
    """Carrega o modelo de embedding e a coleção ChromaDB."""
    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    collection = client.get_collection(name=COLLECTION_NAME)
    return model, collection


# === Mapeamento de versões de documentos ===
# Agrupa doc_ids que são versões do mesmo procedimento base
VERSION_GROUPS = {
    "PROC-042": ["PROC-042", "PROC-042-v2"],
}

# Boost/penalidade para versões
VERSION_BOOST = 0.05  # Boost para versão mais recente
VERSION_PENALTY = -0.05  # Penalidade para versão desatualizada

# Boost por tipo de fonte quando query é sobre regras/políticas
# Nota: NÃO penalizar FAQ — às vezes o FAQ é a resposta correta
# (ex: "Existe tier Platinum?" → FAQ Item 15 é a resposta ideal)
SOURCE_TYPE_BOOST = {
    "normativo": 0.02,
    "informal": 0.0,
}

# === Query Expansion ===
# Mapeamento de termos frequentes → expansões com sinônimos/termos técnicos
QUERY_EXPANSIONS = {
    r"\bfrete\b": "frete transporte logística",
    r"\bfrete especial\b": "frete especial cálculo multiplicador peso acima 500kg",
    r"\bmultiplicador\b": "multiplicador regional fator tabela frete",
    r"\bsudeste\b": "Sudeste região SP RJ MG ES",
    r"\bdevolução\b": "devolução devolver retorno mercadoria prazo",
    r"\bdevolver\b": "devolver devolução retorno mercadoria prazo",
    r"\bprazo\b": "prazo dias úteis período limite",
    r"\bSLA\b": "SLA nível serviço tempo atendimento",
    r"\bcarga perigosa\b": "carga perigosa mercadoria risco exceção restrição",
    r"\bplatinum\b": "Platinum tier cliente categoria nível",
    r"\bgold\b": "Gold tier cliente categoria nível",
    r"\bsilver\b": "Silver tier cliente categoria nível",
    r"\bgarantia\b": "garantia cobertura seguro proteção",
    r"\breclamação\b": "reclamação queixa contestação insatisfação",
}


def expand_query(query: str) -> str:
    """
    Expande a query com sinônimos e termos técnicos relevantes.

    Usa regras baseadas em regex para adicionar termos que melhoram
    o recall sem alterar a semântica original da busca.
    """
    expanded_terms = set()

    for pattern, expansion in QUERY_EXPANSIONS.items():
        if re.search(pattern, query, re.IGNORECASE):
            expanded_terms.update(expansion.split())

    if not expanded_terms:
        return query

    # Remove termos que já estão na query original
    query_words = set(query.lower().split())
    new_terms = expanded_terms - query_words

    if new_terms:
        return f"{query} {' '.join(new_terms)}"
    return query


def apply_version_boost(results: list[SearchResult]) -> list[SearchResult]:
    """
    Aplica boost/penalidade de score baseado na versão do documento.

    Quando existem chunks de v1 e v2 do mesmo procedimento nos resultados,
    a versão mais recente recebe boost e a mais antiga recebe penalidade.
    """
    # Identificar doc_ids presentes nos resultados
    present_doc_ids = {r.metadata.get("doc_id", "") for r in results}

    # Para cada grupo de versão, verificar se múltiplas versões estão presentes
    boost_map = {}  # doc_id -> boost value
    for base, versions in VERSION_GROUPS.items():
        present_in_group = [v for v in versions if v in present_doc_ids]
        if len(present_in_group) < 2:
            continue
        newest = versions[-1]
        for v in present_in_group:
            boost_map[v] = VERSION_BOOST if v == newest else VERSION_PENALTY

    # Aplicar boosts
    for result in results:
        boost = boost_map.get(result.metadata.get("doc_id", ""), 0)
        if boost:
            result.score = min(1.0, max(0.0, result.score + boost))

    return results


def apply_source_type_boost(results: list[SearchResult], query: str) -> list[SearchResult]:
    """
    Aplica boost baseado no source_type quando a query é sobre regras/políticas.

    Queries que mencionam termos normativos recebem boost em docs normativos
    e penalidade em docs informais (FAQ).
    """
    normative_indicators = [
        "regra", "política", "procedimento", "norma", "prazo",
        "obrigatório", "proibido", "oficialmente", "fórmula", "cálculo",
    ]

    query_lower = query.lower()
    is_normative_query = any(term in query_lower for term in normative_indicators)

    if not is_normative_query:
        return results

    for result in results:
        source_type = result.metadata.get("source_type", "unknown")
        boost = SOURCE_TYPE_BOOST.get(source_type, 0)
        if boost != 0:
            result.score = min(1.0, max(0.0, result.score + boost))

    return results


def search(
    query: str,
    model: SentenceTransformer,
    collection,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_RELEVANCE_SCORE,
    filter_metadata: dict | None = None,
    use_query_expansion: bool = True,
) -> list[SearchResult]:
    """
    Busca chunks relevantes para a query usando estratégia de dois passes.

    Passo 1: Busca com a query original (prioriza precisão)
    Passo 2: Busca com query expandida (adiciona recall)
    Merge: Combina resultados, mantendo o maior score por chunk_id

    Essa estratégia evita que a expansão dilua o embedding da query original,
    preservando matches exatos (ex: POL-001 §3.2 para "carga perigosa")
    enquanto ainda recupera chunks adicionais relevantes.

    Args:
        query: Pergunta do atendente em linguagem natural
        model: Modelo de embedding carregado
        collection: Coleção ChromaDB
        top_k: Número máximo de chunks a retornar (default: 5)
        min_score: Score mínimo de similaridade (default: 0.65)
        filter_metadata: Filtro opcional por metadados (ex: {"doc_id": "POL-001"})
        use_query_expansion: Se True, faz segundo passe com query expandida

    Returns:
        Lista de SearchResult ordenada por score decrescente,
        filtrada pelo threshold mínimo, com boost de versão e source_type aplicados.
    """
    # === Passo 1: Busca com query original (precisão) ===
    query_embedding = model.encode(query).tolist()
    primary_results = _execute_search(query_embedding, collection, filter_metadata)

    # === Passo 2: Busca com query expandida (recall adicional) ===
    if use_query_expansion:
        expanded_query = expand_query(query)
        if expanded_query != query:
            expanded_embedding = model.encode(expanded_query).tolist()
            secondary_results = _execute_search(expanded_embedding, collection, filter_metadata)

            # Merge: manter o MAIOR score para cada chunk_id entre os dois passes.
            # A query expandida costuma representar melhor a intenção do usuário
            # para chunks técnicos (ex: §3.2 "carga perigosa"), então adotamos o
            # melhor score de cada chunk em vez de preservar apenas o do passo 1.
            results_map = {r.chunk_id: r for r in primary_results}
            for r in secondary_results:
                existing = results_map.get(r.chunk_id)
                if existing is None or r.score > existing.score:
                    results_map[r.chunk_id] = r
            primary_results = list(results_map.values())

    # Filtrar pelo threshold mínimo
    search_results = [r for r in primary_results if r.score >= min_score]

    # Ordenar por score decrescente
    search_results.sort(key=lambda r: r.score, reverse=True)

    # Aplicar boost de versão (penaliza docs desatualizados)
    search_results = apply_version_boost(search_results)

    # Aplicar boost por source_type (normativo vs informal)
    search_results = apply_source_type_boost(search_results, query)

    # Re-ordenar após boosts e re-filtrar pelo threshold
    search_results = [r for r in search_results if r.score >= min_score]
    search_results.sort(key=lambda r: r.score, reverse=True)

    # Limitar ao top_k final
    return search_results[:top_k]


def _execute_search(
    query_embedding: list[float],
    collection,
    filter_metadata: dict | None = None,
) -> list[SearchResult]:
    """Executa uma busca no ChromaDB e converte resultados."""
    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": RETRIEVAL_CANDIDATES,
        "include": ["documents", "metadatas", "distances"],
    }

    if filter_metadata:
        query_params["where"] = filter_metadata

    results = collection.query(**query_params)

    # Converter distância coseno para score de similaridade
    search_results = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        score = 1 - (distance / 2)

        result = SearchResult(
            chunk_id=results["ids"][0][i],
            text=results["documents"][0][i],
            score=round(score, 4),
            metadata=results["metadatas"][0][i],
        )
        search_results.append(result)

    return search_results


def reorder_for_prompt(results: list[SearchResult]) -> list[SearchResult]:
    """
    Reordena chunks para mitigar o efeito lost-in-the-middle.

    Regra do system prompt v2 [5-6]:
    - Chunk de maior score: PRIMEIRO
    - Chunk de segundo maior score: POR ÚLTIMO
    - Demais: no meio

    Isso posiciona a informação mais relevante nas posições de
    maior atenção do LLM (início e fim do contexto).
    """
    if len(results) <= 2:
        return results

    # Primeiro (maior score) fica no início
    # Segundo (segundo maior) vai para o final
    # Demais ficam no meio
    reordered = [results[0]]  # Maior score primeiro
    if len(results) > 2:
        reordered.extend(results[2:])  # Meio
    reordered.append(results[1])  # Segundo maior por último

    return reordered


def display_results(query: str, results: list[SearchResult]) -> None:
    """Exibe resultados de busca formatados para debug."""
    print(f"\n{'─' * 60}")
    print(f"QUERY: \"{query}\"")
    print(f"{'─' * 60}")
    print(f"Resultados: {len(results)} chunks (threshold ≥ {MIN_RELEVANCE_SCORE})")

    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] Score: {r.score:.4f} | ID: {r.chunk_id}")
        print(f"      Doc: {r.metadata.get('doc_id')} — {r.metadata.get('section', 'N/A')}")
        print(f"      Tipo: {r.metadata.get('source_type')} | Versão: {r.metadata.get('version')}")
        # Mostrar primeiras 150 chars do texto
        preview = r.text[:150].replace("\n", " ")
        print(f"      Preview: {preview}...")

    print(f"{'─' * 60}\n")


if __name__ == "__main__":
    # Teste rápido de busca
    print("Carregando componentes de busca...")
    model, collection = load_search_components()

    test_queries = [
        "Qual o prazo de devolução?",
        "Posso devolver carga perigosa?",
        "Qual o SLA do cliente Gold?",
    ]

    for query in test_queries:
        results = search(query, model, collection)
        display_results(query, results)
