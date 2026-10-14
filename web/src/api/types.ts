// Mirrors app/schemas/estimations.py and app/schemas/sessions.py — keep them in sync.

export type ProjectType = 'mobile_app' | 'web_saas' | 'internal_tool' | 'data_pipeline'
export type DetailLevel = 'summary' | 'medium' | 'detailed'
export type OutputFormat = 'phases_table' | 'line_items' | 'narrative'
/** Language the model answers in. The API falls back to 'es' for anything else. */
export type ResponseLanguage = 'es' | 'en'
/** Who reads the estimate. Optional on requests (the API infers it); no UI control yet. */
export type Audience = 'executive' | 'pm' | 'developer' | 'default'

/** What the form collects; language (UI + model response) comes from the sidebar. */
export interface EstimationInput {
  description: string
  project_type: ProjectType
  detail_level: DetailLevel
  output_format: OutputFormat
}

export interface EstimationRequest extends EstimationInput {
  language: ResponseLanguage
  audience?: Audience
}

export interface EstimationResponse {
  text: string
  prompt_version: string
  /** True when the answer was served from the response cache (no LLM call). */
  cache_hit: boolean
  /** Tier the prompt was framed for, and the resolver rule that chose it. */
  audience: Audience
  audience_rule: string
}

export type CriticVerdict = 'accept' | 'needs_iteration' | 'reject'

export interface CriticIssue {
  category:
    | 'math_error'
    | 'hallucination'
    | 'scope_mismatch'
    | 'phase_imbalance'
    | 'missing_assumption'
    | 'unrealistic_estimate'
  severity: 'critical' | 'major' | 'minor'
  message: string
}

export interface AcbIteration {
  /** 1-based actor attempt. */
  attempt: number
  verdict: CriticVerdict
  issues: CriticIssue[]
}

/** POST /estimate/acb (Actor-Critic-Boss). Mirrored for a future UI; no client function yet. */
export interface AcbResponse {
  estimation: string
  prompt_version: string
  audience: Audience
  audience_rule: string
  /** needs_iteration here means the iteration budget ran out with issues still open. */
  final_verdict: CriticVerdict
  iterations: AcbIteration[]
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
  /** Turns kept verbatim after leaving the window (commitments such as an NDA or a frozen scope). */
  anchors_count: number
  /** Length of the running summary of the turns folded out of the window. */
  summary_chars: number
  /** Tier and resolver rule of the latest turn; null before the first one. */
  last_audience: Audience | null
  last_audience_rule: string | null
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
