export interface QueryHistoryTurn {
  role: "user" | "assistant";
  content: string;
}

export interface QueryRequest {
  question: string;
  history?: QueryHistoryTurn[];
}

export interface SourceDocument {
  id: string;
  title: string;
  path?: string;
  version?: string;
}

export interface RetrievedChunk {
  content: string;
  sourceDocument: SourceDocument;
  score: number;
  isCurrent: boolean;
  supersededBy?: string;
}

export interface QueryResponse {
  answer: string;
  sourceDocuments: SourceDocument[];
}
