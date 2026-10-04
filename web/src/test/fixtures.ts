import type {
  EstimationRequest,
  GenerationMeta,
  ProjectMetadata,
  SessionDetail,
  SessionEstimationResponse,
  SessionSummary,
} from '../api/types'

export const REQUEST: EstimationRequest = {
  description: 'Portal interno para reservar salas con calendario.',
  project_type: 'web_saas',
  detail_level: 'medium',
  output_format: 'line_items',
  language: 'es',
}

export const DONE_META: GenerationMeta = { prompt_version: 'v1', cache_hit: false }

export const METADATA: ProjectMetadata = {
  project_name: 'Portal de reservas',
  assumed_team_size: 4,
  mentioned_technologies: ['React', 'FastAPI'],
  agreed_scope: 'MVP con calendario',
}

export const sessionEstimate = (overrides: Partial<SessionEstimationResponse> = {}): SessionEstimationResponse => ({
  text: '## Estimación',
  prompt_version: 'v1',
  cache_hit: false,
  project_metadata: METADATA,
  history_turns: 1,
  ...overrides,
})

export const sessionSummary = (overrides: Partial<SessionSummary> = {}): SessionSummary => ({
  session_id: 'abcdef123456',
  project_name: 'Portal de reservas',
  history_turns: 2,
  created_at: '2026-01-01T10:00:00Z',
  updated_at: '2026-01-01T11:00:00Z',
  ...overrides,
})

export const sessionDetail = (overrides: Partial<SessionDetail> = {}): SessionDetail => ({
  session_id: 'abcdef123456',
  project_metadata: METADATA,
  history_turns: 2,
  last_estimate: '## Última estimación',
  created_at: '2026-01-01T10:00:00Z',
  updated_at: '2026-01-01T11:00:00Z',
  ...overrides,
})

export const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

export const pdf = (name = 'brief.pdf'): File => new File(['%PDF'], name, { type: 'application/pdf' })
