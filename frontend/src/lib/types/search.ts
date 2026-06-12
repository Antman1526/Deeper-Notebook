// Search types
export interface SearchRequest {
  query: string
  type: 'text' | 'vector'
  limit: number
  search_sources: boolean
  search_notes: boolean
  minimum_score: number
}

export interface SearchResult {
  id: string
  title: string
  parent_id: string
  final_score: number
  matches?: string[]
  relevance?: number
  similarity?: number
  score?: number
  type?: string
  source_type?: string
  created: string
  updated: string
}

export interface SearchResponse {
  results: SearchResult[]
  total_count: number
  search_type: string
}

// Ask types
export interface AskRequest {
  question: string
  strategy_model: string
  answer_model: string
  final_answer_model: string
}

export interface AskResponse {
  answer: string
  question: string
}

// SSE Streaming types
export interface StrategyData {
  reasoning: string
  searches: Array<{
    term: string
    instructions: string
  }>
}

export interface AskStreamEvent {
  // v0.7.43 — `final_answer_delta` added for per-token streaming of
  // the final-synthesis phase. Consumers append `content` chunks to
  // a running buffer; `final_answer` arrives once at the end with the
  // canonical full text.
  type:
    | 'strategy'
    | 'answer'
    | 'final_answer_delta'
    | 'final_answer'
    | 'complete'
    | 'error'
  reasoning?: string
  searches?: Array<{ term: string; instructions: string }>
  content?: string
  final_answer?: string
  message?: string
}
