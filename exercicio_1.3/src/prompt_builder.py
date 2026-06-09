"""
Montagem de Prompt — NovaTech RAG PoC

Monta o prompt completo para envio ao LLM, compondo:
1. System prompt (estático) — identity, constraints, rules, format
2. Conversation history (dinâmico, opcional) — últimas 4 trocas
3. Document context (dinâmico) — chunks recuperados pelo search
4. Pergunta do usuário (dinâmico) — último elemento do prompt

A montagem segue as regras do orchestrator definidas no system prompt v2:
- Chunks ordenados: maior relevância PRIMEIRO, segundo maior POR ÚLTIMO
- Formato estruturado por chunk com metadados
- Threshold de score ≥ 0.65
- Se 0 chunks: inserir "[NENHUM DOCUMENTO RECUPERADO PARA ESTA QUERY]"
"""

from datetime import datetime

from config import SYSTEM_PROMPT_PATH
from search import SearchResult, reorder_for_prompt


def load_system_prompt() -> str:
    """Carrega o system prompt v2 do arquivo."""
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def build_document_context(results: list[SearchResult]) -> str:
    """
    Monta a seção <document_context> do prompt com os chunks recuperados.

    Formato definido no system prompt v2:
    - Máximo 5 chunks
    - Ordenação: maior score primeiro, segundo maior por último
    - Metadados por chunk: documento, versão, seção, data, score
    """
    if not results:
        return "[NENHUM DOCUMENTO RECUPERADO PARA ESTA QUERY]"

    # Reordenar para mitigar lost-in-the-middle
    ordered_results = reorder_for_prompt(results)
    total = len(ordered_results)

    chunks_text = []
    for i, result in enumerate(ordered_results, 1):
        chunk_block = (
            f"[CHUNK {i} de {total}]\n"
            f"Documento  : {result.metadata.get('doc_id', 'N/A')} — {result.metadata.get('doc_title', 'N/A')}\n"
            f"Versão     : {result.metadata.get('version', 'N/A')}\n"
            f"Seção      : {result.metadata.get('section', 'N/A')}\n"
            f"Extraído em: {datetime.now().strftime('%d/%m/%Y')}\n"
            f"Relevância : {result.score:.4f}\n"
            f"Conteúdo   :\n"
            f"{result.metadata.get('doc_id', '')}, {result.metadata.get('section', '')}: "
            f"{result.text}\n"
            f"---"
        )
        chunks_text.append(chunk_block)

    return "\n\n".join(chunks_text)


def build_conversation_history(history: list[dict] | None = None) -> str:
    """
    Monta a seção <conversation_history> com as últimas 4 trocas.

    Args:
        history: Lista de dicts com {"role": "user"|"assistant", "content": str}
                 Se None ou vazia, retorna string vazia (omitir do prompt).

    Orçamento: 400 tokens (~300 palavras). Trunca turnos antigos primeiro.
    """
    if not history:
        return ""

    # Limitar a últimas 4 trocas (8 mensagens: 4 user + 4 assistant)
    max_messages = 8
    recent = history[-max_messages:]

    lines = []
    for msg in recent:
        role = "Atendente" if msg["role"] == "user" else "Assistente"
        lines.append(f"{role}: {msg['content']}")

    history_text = "\n".join(lines)

    # Truncar se exceder ~300 palavras (orçamento 400 tokens)
    words = history_text.split()
    if len(words) > 300:
        history_text = " ".join(words[-300:])
        history_text = "[...histórico truncado...]\n" + history_text

    return history_text


def build_full_prompt(
    query: str,
    results: list[SearchResult],
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Monta o prompt completo pronto para envio ao LLM.

    Estrutura:
    1. System prompt (estático)
    2. <conversation_history> (dinâmico, se houver)
    3. <document_context> (dinâmico — chunks)
    4. Pergunta do usuário (último elemento)

    O <ticket_data> não é incluído neste PoC (dados de chamado não disponíveis).
    """
    # 1. System prompt base (estático)
    system_prompt = load_system_prompt()

    # 2. Substituir placeholder de conversation_history
    history_content = build_conversation_history(conversation_history)
    system_prompt = system_prompt.replace("{CONVERSATION_HISTORY}", history_content)

    # 3. Substituir placeholder de document_context
    document_context = build_document_context(results)
    system_prompt = system_prompt.replace("{CHUNKS_RECUPERADOS}", document_context)

    # 4. Substituir placeholder da query (no ticket_data)
    # Como ticket_data não é usado, adicionamos a query diretamente ao final
    # Remover a seção ticket_data do template e adicionar query diretamente
    query_block = (
        f"\n---\n\n"
        f"Pergunta do atendente:\n"
        f"{query}"
    )

    # Montar prompt final
    full_prompt = system_prompt + query_block

    return full_prompt


def estimate_tokens(text: str) -> int:
    """
    Estima o número de tokens para texto em português.
    Regra: ~0.62 palavras/token (exercício 1.1).
    """
    word_count = len(text.split())
    return int(word_count / 0.62)


def display_prompt_stats(prompt: str, query: str, results: list[SearchResult]) -> None:
    """Exibe estatísticas do prompt montado."""
    estimated_tokens = estimate_tokens(prompt)

    print(f"\n{'═' * 60}")
    print(f"ESTATÍSTICAS DO PROMPT MONTADO")
    print(f"{'═' * 60}")
    print(f"  Query: \"{query}\"")
    print(f"  Chunks no contexto: {len(results)}")
    print(f"  Caracteres totais: {len(prompt):,}")
    print(f"  Palavras totais: {len(prompt.split()):,}")
    print(f"  Tokens estimados: ~{estimated_tokens:,}")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    # Teste rápido de montagem de prompt
    from search import load_search_components, search

    print("Carregando componentes...")
    model, collection = load_search_components()

    test_query = "Qual o prazo de devolução para carga perigosa?"
    results = search(test_query, model, collection)

    prompt = build_full_prompt(test_query, results)
    display_prompt_stats(prompt, test_query, results)

    # Salvar prompt montado para inspeção
    output_path = SYSTEM_PROMPT_PATH.parent.parent / "results" / "sample_prompt.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")
    print(f"\n  Prompt salvo em: {output_path}")
