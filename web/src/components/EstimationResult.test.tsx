import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { EstimationState } from '../hooks/useSession'
import { DONE_META } from '../test/fixtures'
import { withLocale } from '../test/render'
import { EstimationResult } from './EstimationResult'

const MARKDOWN = `## Estimación: Reservas

| Fase | Horas |
|---|---|
| Diseño | 32 |

**Total estimado: 232 horas**
**Duración estimada: 3-4 semanas**`

const state = (overrides: Partial<EstimationState>): EstimationState => ({
  status: 'idle',
  text: '',
  meta: null,
  error: null,
  ...overrides,
})

describe('EstimationResult', () => {
  it('renders nothing before the first request', () => {
    const { container } = withLocale(<EstimationResult state={state({})} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a busy placeholder while waiting for the response', () => {
    withLocale(<EstimationResult state={state({ status: 'loading' })} />)

    expect(screen.getByLabelText('Generando estimación')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Estimación' })).toHaveAttribute('aria-busy', 'true')
  })

  it('renders English chrome when the locale is English', () => {
    withLocale(<EstimationResult state={state({ status: 'loading' })} />, 'en')

    expect(screen.getByLabelText('Generating estimate')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Estimate' })).toBeInTheDocument()
  })

  it('renders the finished Markdown (tables, separate closing lines) and the prompt version', () => {
    withLocale(<EstimationResult state={state({ status: 'done', text: MARKDOWN, meta: DONE_META })} />)

    expect(screen.getByRole('heading', { name: 'Estimación: Reservas' })).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('Diseño')).toBeInTheDocument()
    const total = screen.getByText('Total estimado: 232 horas')
    // The closing lines must not collapse into one paragraph.
    expect(total.nextElementSibling?.tagName).toBe('BR')

    expect(screen.getByText('v1')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Estimación' })).toHaveAttribute('aria-busy', 'false')
  })

  it('shows a cached chip only for cache hits', () => {
    const { rerender } = withLocale(
      <EstimationResult state={state({ status: 'done', text: 'Hecho', meta: { prompt_version: 'v1', cache_hit: true } })} />,
      'en',
    )
    expect(screen.getByText('cached')).toBeInTheDocument()

    rerender(<EstimationResult state={state({ status: 'done', text: 'Hecho', meta: DONE_META })} />)
    expect(screen.queryByText('cached')).not.toBeInTheDocument()
  })

  it('shows errors as an alert', () => {
    withLocale(<EstimationResult state={state({ status: 'error', error: 'Error HTTP 502: El proveedor LLM falló.' })} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Error HTTP 502: El proveedor LLM falló.')
  })
})
