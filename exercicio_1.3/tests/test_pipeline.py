"""
Testes do Pipeline RAG — NovaTech PoC

Executa o pipeline completo (ingestão → busca → montagem de prompt)
para 6 perguntas do mapa de cobertura do Anexo B.

Para cada pergunta, documenta:
- Chunks recuperados (id + texto resumido)
- Score de similaridade
- Comparação com gabarito do Anexo B (match/miss)
- Prompt montado (salvo em arquivo para teste manual no Claude)

Gabarito extraído do Anexo B — Mapa de cobertura:
| Pergunta                           | Chunks esperados (DEVEM ser recuperados)       |
|------------------------------------|------------------------------------------------|
| "Qual o prazo de devolução?"       | POL-001-A, POL-001-B                           |
| "Posso devolver carga perigosa?"   | POL-001-B                                      |
| "Qual o SLA do cliente Gold?"      | SLA-2024-B                                     |
| "Qual o SLA do cliente Platinum?"  | SLA-2024-A (não existem outros tiers)          |
| "Frete para 600kg para Manaus?"    | PROC-042v2-B, PROC-042v2-A                     |
| "Qual o multiplicador para o Sudeste?" | PROC-042v2-B                               |
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from config import CHROMA_DB_DIR, COLLECTION_NAME
from prompt_builder import (build_full_prompt, display_prompt_stats,
                            estimate_tokens)
from search import (SearchResult, display_results, load_search_components,
                    search)

# === Gabarito do Anexo B ===
# Chunks esperados por pergunta (mapeados para os doc_ids do nosso pipeline)
TEST_CASES = [
    {
        "query": "Qual o prazo de devolução?",
        "expected_docs": ["POL-001"],
        "expected_content_keywords": ["7 dias úteis", "7 (sete) dias úteis", "devolução"],
        "description": "Deve retornar POL-001 com prazo de 7 dias úteis + exceções",
    },
    {
        "query": "Posso devolver carga perigosa?",
        "expected_docs": ["POL-001"],
        "expected_content_keywords": ["NÃO são elegíveis", "classes 1 a 6", "carga perigosa", "Gestão de Riscos"],
        "description": "Deve retornar POL-001 seção 3.2 — cargas perigosas NÃO podem ser devolvidas",
    },
    {
        "query": "Qual o SLA do cliente Gold?",
        "expected_docs": ["SLA-2024"],
        "expected_content_keywords": ["Gold", "2h", "24h", "resposta"],
        "description": "Deve retornar SLA-2024 com tempos Gold: resposta 2h, resolução 24h",
    },
    {
        "query": "Qual o SLA do cliente Platinum?",
        "expected_docs": ["SLA-2024"],
        "expected_content_keywords": ["3 (três) tiers", "Gold, Silver e Standard", "não existem outros tiers", "Não existe tier Platinum"],
        "description": "Deve retornar SLA-2024-A dizendo que só existem 3 tiers (Gold/Silver/Standard)",
    },
    {
        "query": "Frete para 600kg para Manaus?",
        "expected_docs": ["PROC-042-v2"],
        "expected_content_keywords": ["1.8", "Norte", "500kg", "multiplicador"],
        "description": "Deve retornar PROC-042-v2 com multiplicador Norte = 1.8",
    },
    {
        "query": "Qual o multiplicador de frete para o Sudeste?",
        "expected_docs": ["PROC-042-v2"],
        "expected_content_keywords": ["1.1", "Sudeste"],
        "description": "Deve retornar PROC-042-v2 com multiplicador Sudeste = 1.1 (risco: v1 diz 1.0)",
    },
]


def evaluate_result(test_case: dict, results: list[SearchResult]) -> dict:
    """
    Avalia se os chunks recuperados correspondem ao gabarito.

    Retorna dict com:
    - match: bool (ao menos 1 chunk esperado no top-k)
    - matched_docs: quais docs esperados foram encontrados
    - missed_docs: quais docs esperados NÃO foram encontrados
    - keyword_hits: quais keywords do gabarito aparecem nos chunks
    - unexpected_docs: docs recuperados que não eram esperados
    """
    retrieved_doc_ids = [r.metadata.get("doc_id", "") for r in results]
    retrieved_texts = " ".join([r.text for r in results]).lower()

    expected_docs = test_case["expected_docs"]
    keywords = test_case["expected_content_keywords"]

    matched_docs = [doc for doc in expected_docs if doc in retrieved_doc_ids]
    missed_docs = [doc for doc in expected_docs if doc not in retrieved_doc_ids]
    unexpected_docs = [doc for doc in set(retrieved_doc_ids) if doc not in expected_docs]
    keyword_hits = [kw for kw in keywords if kw.lower() in retrieved_texts]
    keyword_misses = [kw for kw in keywords if kw.lower() not in retrieved_texts]

    return {
        "match": len(matched_docs) > 0,
        "matched_docs": matched_docs,
        "missed_docs": missed_docs,
        "unexpected_docs": list(set(unexpected_docs)),
        "keyword_hits": keyword_hits,
        "keyword_misses": keyword_misses,
        "total_results": len(results),
    }


def run_tests():
    """Executa todos os testes e gera relatório."""
    print("=" * 70)
    print("TESTE DO PIPELINE RAG — NovaTech PoC")
    print(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 70)

    # Carregar componentes
    print("\nCarregando modelo de embedding e ChromaDB...")
    try:
        model, collection = load_search_components()
    except Exception as e:
        print(f"\n❌ ERRO: Não foi possível carregar o ChromaDB.")
        print(f"   Certifique-se de executar 'python ingest.py' primeiro.")
        print(f"   Erro: {e}")
        sys.exit(1)

    print(f"   ✓ Coleção '{COLLECTION_NAME}' carregada com {collection.count()} chunks")

    # Executar testes
    results_dir = Path(__file__).resolve().parent.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    report = []
    total_match = 0
    total_keyword_coverage = 0

    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n{'━' * 70}")
        print(f"TESTE {i}/{len(TEST_CASES)}: \"{test_case['query']}\"")
        print(f"Expectativa: {test_case['description']}")
        print(f"{'━' * 70}")

        # Buscar
        search_results = search(test_case["query"], model, collection)
        display_results(test_case["query"], search_results)

        # Avaliar
        evaluation = evaluate_result(test_case, search_results)

        # Status
        status = "✓ PASS" if evaluation["match"] else "✗ FAIL"
        print(f"\n  Resultado: {status}")
        print(f"  Docs esperados encontrados: {evaluation['matched_docs']}")
        if evaluation["missed_docs"]:
            print(f"  Docs esperados NÃO encontrados: {evaluation['missed_docs']}")
        if evaluation["unexpected_docs"]:
            print(f"  Docs inesperados no resultado: {evaluation['unexpected_docs']}")
        print(f"  Keywords encontradas: {len(evaluation['keyword_hits'])}/{len(test_case['expected_content_keywords'])}")
        if evaluation["keyword_misses"]:
            print(f"  Keywords ausentes: {evaluation['keyword_misses']}")

        if evaluation["match"]:
            total_match += 1

        keyword_ratio = len(evaluation["keyword_hits"]) / max(len(test_case["expected_content_keywords"]), 1)
        total_keyword_coverage += keyword_ratio

        # Montar prompt e salvar
        prompt = build_full_prompt(test_case["query"], search_results)
        prompt_file = results_dir / f"prompt_test_{i}.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        # Armazenar no relatório
        report.append({
            "test_number": i,
            "query": test_case["query"],
            "description": test_case["description"],
            "status": "PASS" if evaluation["match"] else "FAIL",
            "evaluation": evaluation,
            "chunks_retrieved": [
                {
                    "id": r.chunk_id,
                    "doc_id": r.metadata.get("doc_id"),
                    "section": r.metadata.get("section"),
                    "score": r.score,
                    "preview": r.text[:200],
                }
                for r in search_results
            ],
            "prompt_file": str(prompt_file.name),
            "prompt_tokens_estimated": estimate_tokens(prompt),
        })

    # Resumo final
    print(f"\n\n{'═' * 70}")
    print("RESUMO DOS TESTES")
    print(f"{'═' * 70}")
    print(f"  Total de testes:    {len(TEST_CASES)}")
    print(f"  Passaram (PASS):    {total_match}/{len(TEST_CASES)}")
    print(f"  Falharam (FAIL):    {len(TEST_CASES) - total_match}/{len(TEST_CASES)}")
    print(f"  Cobertura keywords: {total_keyword_coverage / len(TEST_CASES) * 100:.1f}%")
    print(f"\n  Prompts salvos em:  {results_dir}/")
    print(f"  (Cole no Claude para avaliar as respostas geradas)")
    print(f"{'═' * 70}")

    # Salvar relatório JSON
    report_file = results_dir / "test_report.json"
    report_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  Relatório JSON:     {report_file}")

    return report


if __name__ == "__main__":
    run_tests()
