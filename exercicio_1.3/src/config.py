"""Configuração central do pipeline RAG — NovaTech."""

from pathlib import Path

# === Paths ===
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT.parent / "documentacao"
CHROMA_DB_DIR = PROJECT_ROOT / "chroma_db"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.md"

# === Documentos para ingestão ===
# Apenas os 5 documentos-chave da NovaTech (exclui anexos)
DOCUMENT_FILES = [
    "POL-001-politica-devolucao.md",
    "PROC-042-frete-especial-v1.md",
    "PROC-042-v2-frete-especial-revisado.md",
    "SLA-2024-tabela-sla-clientes.md",
    "FAQ-atendimento.md",
]

# === Modelo de Embedding ===
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

# === Parâmetros de Chunking ===
# Estratégia: chunking semântico por seção markdown (H2/H3)
# Justificativa (exercício 1.1): perguntas de política/regra exigem
# chunks médios (~400-500 tokens) por seção semântica, com overlap
# de 15-20% para não perder contexto nas fronteiras.
CHUNK_SIZE = 800  # ~400-500 tokens para português (0.62 palavras/token)
CHUNK_OVERLAP = 150  # ~15-20% de overlap (~75-100 tokens)
CHUNK_SEPARATORS = ["\n## ", "\n### ", "\n\n", "\n"]

# === ChromaDB ===
COLLECTION_NAME = "novatech_docs"

# === Retrieval ===
DEFAULT_TOP_K = 5  # Máximo de chunks por query (regra do system prompt v2)
MIN_RELEVANCE_SCORE = 0.65  # Threshold mínimo (regra do orchestrator no system prompt v2)
MAX_CHUNKS_TOKENS = 1200  # Orçamento de tokens para chunks no prompt

# === Metadados de documento ===
# Mapeamento doc_id → metadados extraídos dos cabeçalhos
DOC_METADATA = {
    "POL-001-politica-devolucao.md": {
        "doc_id": "POL-001",
        "doc_title": "Política de Devolução de Mercadorias",
        "version": "3.1",
        "date": "15/01/2024",
        "responsible": "Diretoria de Operações",
        "source_type": "normativo",
    },
    "PROC-042-frete-especial-v1.md": {
        "doc_id": "PROC-042",
        "doc_title": "Procedimento de Cálculo de Frete Especial",
        "version": "1.0",
        "date": "03/03/2023",
        "responsible": "Diretoria Comercial",
        "source_type": "normativo",
    },
    "PROC-042-v2-frete-especial-revisado.md": {
        "doc_id": "PROC-042-v2",
        "doc_title": "Procedimento de Cálculo de Frete Especial (Revisado)",
        "version": "2.0",
        "date": "15/11/2023",
        "responsible": "Diretoria Comercial",
        "source_type": "normativo",
    },
    "SLA-2024-tabela-sla-clientes.md": {
        "doc_id": "SLA-2024",
        "doc_title": "Tabela de SLA por Tipo de Cliente",
        "version": "2024.1",
        "date": "01/01/2024",
        "responsible": "Diretoria Comercial",
        "source_type": "normativo",
    },
    "FAQ-atendimento.md": {
        "doc_id": "FAQ-Atendimento",
        "doc_title": "Perguntas Frequentes do Time de Suporte",
        "version": "não controlada",
        "date": "diversas",
        "responsible": "Time de Atendimento (informal)",
        "source_type": "informal",
    },
}
