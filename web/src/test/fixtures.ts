import type { EstimationRequest, GenerationMeta, ProjectMetadata, SessionEstimationResponse } from '../api/types'

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

export const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

export const pdf = (name = 'brief.pdf'): File => new File(['%PDF'], name, { type: 'application/pdf' })
