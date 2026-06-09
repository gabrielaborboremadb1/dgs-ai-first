"""
Módulo de Busca — NovaTech RAG PoC

Recebe uma pergunta em texto natural, gera o embedding da query,
busca os top-k chunks mais similares no ChromaDB, e retorna os
resultados com score de similaridade e metadados.

Regras de retrieval (definidas no system prompt v2):
- Máximo: 5 chunks por query
- Descartar chunks com score < 0.65
- Ordenação para injeção no prompt: maior score PRIMEIRO,
  segundo maior POR ÚLTIMO, demais no meio (mitiga lost-in-the-middle)
"""

from dataclasses import dataclass

import chromadb
from config import (CHROMA_DB_DIR, COLLECTION_NAME, DEFAULT_TOP_K,
                    EMBEDDING_MODEL, MIN_RELEVANCE_SCORE)
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


def search(
    query: str,
    model: SentenceTransformer,
    collection,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_RELEVANCE_SCORE,
    filter_metadata: dict | None = None,
) -> list[SearchResult]:
    """
    Busca chunks relevantes para a query.

    Args:
        query: Pergunta do atendente em linguagem natural
        model: Modelo de embedding carregado
        collection: Coleção ChromaDB
        top_k: Número máximo de chunks a retornar (default: 5)
        min_score: Score mínimo de similaridade (default: 0.65)
        filter_metadata: Filtro opcional por metadados (ex: {"doc_id": "POL-001"})

    Returns:
        Lista de SearchResult ordenada por score decrescente,
        filtrada pelo threshold mínimo.
    """
    # Gerar embedding da query
    query_embedding = model.encode(query).tolist()

    # Preparar parâmetros de busca
    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }

    if filter_metadata:
        query_params["where"] = filter_metadata

    # Executar busca
    results = collection.query(**query_params)

    # Converter distância coseno para score de similaridade
    # ChromaDB com espaço coseno retorna distância (0 = idêntico, 2 = oposto)
    # Score = 1 - (distância / 2) para normalizar em [0, 1]
    search_results = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        score = 1 - (distance / 2)

        if score < min_score:
            continue

        result = SearchResult(
            chunk_id=results["ids"][0][i],
            text=results["documents"][0][i],
            score=round(score, 4),
            metadata=results["metadatas"][0][i],
        )
        search_results.append(result)

    # Ordenar por score decrescente
    search_results.sort(key=lambda r: r.score, reverse=True)

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
