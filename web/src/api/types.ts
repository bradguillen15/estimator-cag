// Mirrors app/schemas/estimations.py and app/schemas/sessions.py — keep them in sync.

export type ProjectType = 'mobile_app' | 'web_saas' | 'internal_tool' | 'data_pipeline'
export type DetailLevel = 'summary' | 'medium' | 'detailed'
export type OutputFormat = 'phases_table' | 'line_items' | 'narrative'
/** Language the model answers in. The API falls back to 'es' for anything else. */
export type ResponseLanguage = 'es' | 'en'

/** What the form collects; language (UI + model response) comes from the sidebar. */
export interface EstimationInput {
  description: string
  project_type: ProjectType
  detail_level: DetailLevel
  output_format: OutputFormat
}

export interface EstimationRequest extends EstimationInput {
  language: ResponseLanguage
}

export interface EstimationResponse {
  text: string
  prompt_version: string
  /** True when the answer was served from the response cache (no LLM call). */
  cache_hit: boolean
}

export interface PromptContext {
  prompt_version: string
  examples_markdown: string
}

/** Generation details shown next to the estimate. */
export interface GenerationMeta {
  prompt_version: string
  /** True when the answer was served from the response cache (no LLM call). */
  cache_hit: boolean
}

/** Facts about the project that the server extracts and remembers across turns. */
export interface ProjectMetadata {
  project_name: string | null
  assumed_team_size: number | null
  mentioned_technologies: string[]
  agreed_scope: string | null
}

export const EMPTY_PROJECT_METADATA: ProjectMetadata = {
  project_name: null,
  assumed_team_size: null,
  mentioned_technologies: [],
  agreed_scope: null,
}

export interface SessionCreatedResponse {
  session_id: string
}

/** One row of GET /sessions: only sessions with at least one turn are listed. */
export interface SessionSummary {
  session_id: string
  project_name: string | null
  history_turns: number
  created_at: string
  updated_at: string
}

/** One turn of a session as GET /sessions/{id} returns it: what was typed and the estimate it got. */
export interface SessionTurnView {
  /** The transcript as typed, without the text extracted from attachments. */
  description: string
  attachment_names: string[]
  estimate: string
  prompt_version: string
  cache_hit: boolean
  created_at: string
}

/** GET /sessions/{id}: what the UI needs to resume a session. */
export interface SessionDetail {
  session_id: string
  project_metadata: ProjectMetadata
  history_turns: number
  /** Oldest first; capped by the server's history window. */
  turns: SessionTurnView[]
  created_at: string
  updated_at: string
}

export interface SessionEstimationResponse extends EstimationResponse {
  project_metadata: ProjectMetadata
  /** Turns currently held in the server's sliding history window. */
  history_turns: number
}

export const DESCRIPTION_MIN = 20
export const DESCRIPTION_MAX = 20000

/** Max files per request. Mirrors app/services/attachments.py. */
export const MAX_ATTACHMENTS = 5

/** UI default: English. The API's own default stays 'es' for other clients, so the UI always sends `language`. */
export const DEFAULT_RESPONSE_LANGUAGE: ResponseLanguage = 'en'

/** Supported UI + model response languages. Labels live in i18n. */
export const RESPONSE_LANGUAGES: readonly ResponseLanguage[] = ['es', 'en']
