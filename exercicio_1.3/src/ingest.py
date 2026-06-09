"""
Pipeline de Ingestão — NovaTech RAG PoC

Etapas:
1. Lê os 5 documentos .md da pasta documentacao/
2. Extrai metadados do cabeçalho de cada documento
3. Divide em chunks semânticos por seção markdown (H2/H3) com overlap
4. Gera embeddings com sentence-transformers (all-MiniLM-L6-v2)
5. Armazena no ChromaDB com metadados enriquecidos

Estratégia de chunking justificada pelo exercício 1.1:
- Chunking semântico por seção (delimitado por H2/H3) preserva unidades
  de significado completas (regras, políticas, procedimentos)
- Overlap de 15-20% evita perda de contexto nas fronteiras entre seções
- Tamanho alvo ~400-500 tokens: adequado para perguntas de política/regra
  que são o tipo mais frequente dos atendentes da NovaTech
- Cabeçalhos de seção preservados em cada chunk como âncora semântica
"""

import re
from pathlib import Path

import chromadb
from config import (CHROMA_DB_DIR, CHUNK_OVERLAP, CHUNK_SEPARATORS, CHUNK_SIZE,
                    COLLECTION_NAME, DOC_METADATA, DOCS_DIR, DOCUMENT_FILES,
                    EMBEDDING_MODEL)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer


def load_document(filepath: Path) -> str:
    """Lê o conteúdo de um documento .md."""
    return filepath.read_text(encoding="utf-8")


def extract_section_header(text: str) -> str:
    """Extrai o primeiro cabeçalho H2 ou H3 presente no texto do chunk."""
    match = re.search(r"^(#{2,3}\s+.+)$", text, re.MULTILINE)
    return match.group(1).strip("# ").strip() if match else "Sem seção identificada"


def create_chunks(text: str, filename: str) -> list[dict]:
    """
    Divide o documento em chunks semânticos por seção markdown.

    Estratégia:
    - Separadores hierárquicos: ## > ### > parágrafo > linha
    - Tamanho alvo: ~800 caracteres (~400-500 tokens para português)
    - Overlap: 150 caracteres (~75-100 tokens, ~15-20%)
    - Preserva cabeçalhos como contexto semântico
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=CHUNK_SEPARATORS,
        keep_separator=True,
        is_separator_regex=False,
    )

    raw_chunks = splitter.split_text(text)
    metadata = DOC_METADATA.get(filename, {})
    doc_title_line = f"[{metadata.get('doc_id', 'UNKNOWN')}] {metadata.get('doc_title', filename)}"

    chunks = []
    for i, chunk_text in enumerate(raw_chunks):
        section = extract_section_header(chunk_text)

        # Prepend document context to chunk for better embedding quality
        contextualized_chunk = f"{doc_title_line} — {section}\n\n{chunk_text}"

        chunk_data = {
            "text": contextualized_chunk,
            "original_text": chunk_text,
            "metadata": {
                "doc_id": metadata.get("doc_id", "UNKNOWN"),
                "doc_title": metadata.get("doc_title", filename),
                "section": section,
                "version": metadata.get("version", "N/A"),
                "date": metadata.get("date", "N/A"),
                "responsible": metadata.get("responsible", "N/A"),
                "source_type": metadata.get("source_type", "unknown"),
                "chunk_index": i,
                "total_chunks": len(raw_chunks),
                "filename": filename,
            },
        }
        chunks.append(chunk_data)

    return chunks


def ingest_documents():
    """Pipeline principal de ingestão."""
    print("=" * 60)
    print("PIPELINE DE INGESTÃO — NovaTech RAG PoC")
    print("=" * 60)

    # 1. Carregar modelo de embeddings
    print(f"\n[1/4] Carregando modelo de embeddings: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"       Modelo carregado. Dimensões: {model.get_embedding_dimension()}")

    # 2. Processar documentos
    print(f"\n[2/4] Processando {len(DOCUMENT_FILES)} documentos de {DOCS_DIR}")
    all_chunks = []
    for filename in DOCUMENT_FILES:
        filepath = DOCS_DIR / filename
        if not filepath.exists():
            print(f"       ⚠️  Arquivo não encontrado: {filepath}")
            continue

        text = load_document(filepath)
        chunks = create_chunks(text, filename)
        all_chunks.extend(chunks)
        print(f"       ✓ {filename}: {len(chunks)} chunks gerados")

    print(f"\n       Total de chunks: {len(all_chunks)}")

    # 3. Gerar embeddings
    print("\n[3/4] Gerando embeddings para todos os chunks...")
    texts_for_embedding = [chunk["text"] for chunk in all_chunks]
    embeddings = model.encode(texts_for_embedding, show_progress_bar=True)
    print(f"       ✓ {len(embeddings)} embeddings gerados ({embeddings.shape[1]} dimensões)")

    # 4. Armazenar no ChromaDB
    print(f"\n[4/4] Armazenando no ChromaDB em {CHROMA_DB_DIR}")
    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))

    # Recriar coleção (limpa dados anteriores para re-ingestão)
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Preparar dados para inserção
    ids = []
    documents = []
    metadatas = []
    embedding_list = []

    for i, chunk in enumerate(all_chunks):
        chunk_id = f"{chunk['metadata']['doc_id']}_chunk_{chunk['metadata']['chunk_index']:03d}"
        ids.append(chunk_id)
        documents.append(chunk["text"])
        metadatas.append(chunk["metadata"])
        embedding_list.append(embeddings[i].tolist())

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embedding_list,
    )

    print(f"       ✓ {collection.count()} chunks armazenados na coleção '{COLLECTION_NAME}'")

    # Resumo
    print("\n" + "=" * 60)
    print("INGESTÃO CONCLUÍDA")
    print("=" * 60)
    print(f"  Documentos processados: {len(DOCUMENT_FILES)}")
    print(f"  Total de chunks:        {len(all_chunks)}")
    print(f"  Modelo de embedding:    {EMBEDDING_MODEL}")
    print(f"  Tamanho do chunk:       {CHUNK_SIZE} chars (~{CHUNK_SIZE // 2} tokens)")
    print(f"  Overlap:                {CHUNK_OVERLAP} chars (~{CHUNK_OVERLAP // 2} tokens)")
    print(f"  ChromaDB path:          {CHROMA_DB_DIR}")
    print("=" * 60)

    return all_chunks


if __name__ == "__main__":
    ingest_documents()
