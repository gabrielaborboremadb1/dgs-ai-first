"""
Pipeline de Ingestão — NovaTech RAG PoC

Etapas:
1. Lê os 5 documentos .md da pasta documentacao/
2. Extrai metadados do cabeçalho de cada documento
3. Remove bloco de cabeçalho/metadata do topo antes do chunking
4. Divide em chunks semânticos por seção markdown (H2/H3) com overlap
5. Gera embeddings com sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)
6. Armazena no ChromaDB com metadados enriquecidos

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
                    EMBEDDING_MODEL, MAX_SECTION_SIZE)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer


def load_document(filepath: Path) -> str:
    """Lê o conteúdo de um documento .md."""
    return filepath.read_text(encoding="utf-8")


def strip_header_metadata(text: str) -> str:
    """
    Remove o bloco de cabeçalho/metadata do topo do documento antes do chunking.

    O cabeçalho típico dos documentos NovaTech segue o padrão:
        # Título
        **Versão:** X.X
        **Data:** DD/MM/AAAA
        **Responsável:** Fulano
        **Classificação:** tipo

    Esse bloco é removido pois já está capturado nos metadados estruturados
    (DOC_METADATA em config.py) e sua presença no chunking dilui a qualidade
    dos embeddings com informação repetitiva e não-semântica.

    Também remove disclaimers/avisos que aparecem antes da primeira seção H2.
    """
    # Encontrar a primeira seção H2 (## ) que marca o início do conteúdo real
    match = re.search(r"^(## .+)$", text, re.MULTILINE)
    if match:
        return text[match.start():]

    # Se não houver H2, retornar texto original (safety fallback)
    return text


def extract_section_header(text: str) -> str:
    """Extrai o primeiro cabeçalho H2 ou H3 presente no texto do chunk."""
    match = re.search(r"^(#{2,3}\s+.+)$", text, re.MULTILINE)
    return match.group(1).strip("# ").strip() if match else "Sem seção identificada"


def create_chunks(text: str, filename: str) -> list[dict]:
    """
    Divide o documento em chunks semânticos por seção markdown.

    Estratégia v4 — chunking hierárquico (H2 → H3):
    1. Remove bloco de cabeçalho/metadata
    2. Divide o documento por seções H2 (## ) como unidade primária
    3. Mantém cada seção H2 inteira (com suas subseções ### ) se couber
       em MAX_SECTION_SIZE — preserva fórmula + tabela juntas
    4. Apenas seções H2 muito longas são subdivididas por H3 (### ),
       com o cabeçalho H2 (e intro) anexado à primeira subseção
    5. Subseções H3 que ainda excedam o limite são divididas por parágrafo

    Isso evita três problemas:
    - Chunks gigantes que misturam §3.1+§3.2 (diluição de embedding)
    - Chunks cortados no meio de uma seção (perda de contexto)
    - Chunks órfãos contendo apenas o cabeçalho H2 (ruído no retrieval)
    """
    # Remover bloco de cabeçalho/metadata do topo
    text = strip_header_metadata(text)

    # Dividir hierarquicamente: H2 inteiro, descendo a H3 só se necessário
    final_sections = split_into_sections(text)

    metadata = DOC_METADATA.get(filename, {})
    doc_title_line = f"[{metadata.get('doc_id', 'UNKNOWN')}] {metadata.get('doc_title', filename)}"

    chunks = []
    for i, chunk_text in enumerate(final_sections):
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
                "total_chunks": len(final_sections),
                "filename": filename,
            },
        }
        chunks.append(chunk_data)

    return chunks


def _split_by_header(text: str, level: int) -> list[str]:
    """
    Divide o texto pelos headers de um nível específico (2 = ##, 3 = ###).

    Cada bloco inclui seu header e tudo até o próximo header do mesmo nível.
    Conteúdo antes do primeiro header é retornado como bloco inicial.
    """
    hashes = "#" * level
    # Header do nível exato (não captura níveis mais profundos como início de bloco)
    header_pattern = re.compile(rf"^({hashes}\s+.+)$", re.MULTILINE)
    matches = list(header_pattern.finditer(text))

    if not matches:
        return [text.strip()] if text.strip() else []

    blocks = []

    # Conteúdo antes do primeiro header deste nível
    if matches[0].start() > 0:
        prefix = text[: matches[0].start()].strip()
        if prefix:
            blocks.append(prefix)

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)

    return blocks


def split_into_sections(text: str) -> list[str]:
    """
    Chunking hierárquico: H2 como unidade atômica, descendo a H3 só se grande.

    - Cada seção H2 (## ) é mantida inteira com suas subseções ### enquanto
      couber em MAX_SECTION_SIZE (ex: fórmula §2 + tabela §2.1 juntas).
    - Se uma seção H2 exceder o limite, ela é dividida por H3 (### ), e o
      cabeçalho H2 + texto introdutório é anexado à PRIMEIRA subseção para
      evitar chunks órfãos contendo apenas o título.
    - Subseções H3 que ainda excedam o limite são divididas por parágrafo.
    """
    h2_blocks = _split_by_header(text, level=2)
    final_sections: list[str] = []

    for block in h2_blocks:
        if len(block) <= MAX_SECTION_SIZE:
            final_sections.append(block)
            continue

        # Seção H2 grande demais: dividir por H3
        h3_parts = _split_by_header(block, level=3)

        # O primeiro elemento é o cabeçalho H2 + intro (sem ### próprio).
        # Anexá-lo à primeira subseção H3 evita chunk órfão de título.
        if len(h3_parts) > 1:
            header_intro = h3_parts[0]
            merged = [f"{header_intro}\n\n{h3_parts[1]}"] + h3_parts[2:]
        else:
            merged = h3_parts

        # Subdividir subseções que ainda excedam o limite
        for part in merged:
            if len(part) <= MAX_SECTION_SIZE:
                final_sections.append(part)
            else:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=CHUNK_SIZE,
                    chunk_overlap=CHUNK_OVERLAP,
                    separators=["\n\n", "\n"],
                    keep_separator=True,
                    is_separator_regex=False,
                )
                final_sections.extend(splitter.split_text(part))

    return final_sections


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
