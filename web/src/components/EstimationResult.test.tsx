import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DONE_META } from '../test/fixtures'
import { withLocale } from '../test/render'
import { ErrorAlert, EstimationResult } from './EstimationResult'
import type { EstimationCardState } from './EstimationResult'

const MARKDOWN = `## Estimación: Reservas

| Fase | Horas |
|---|---|
| Diseño | 32 |

**Total estimado: 232 horas**
**Duración estimada: 3-4 semanas**`

const done = (text: string, meta = DONE_META): EstimationCardState => ({ status: 'done', text, meta })
const loading: EstimationCardState = { status: 'loading' }

describe('EstimationResult', () => {
  it('shows a busy placeholder while waiting for the response', () => {
    withLocale(<EstimationResult state={loading} />)

    expect(screen.getByLabelText('Generando estimación')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Estimación' })).toHaveAttribute('aria-busy', 'true')
  })

  it('renders English chrome when the locale is English', () => {
    withLocale(<EstimationResult state={loading} />, 'en')

    expect(screen.getByLabelText('Generating estimate')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Estimate' })).toBeInTheDocument()
  })

  it('renders the finished Markdown (tables, separate closing lines) and the prompt version', () => {
    withLocale(<EstimationResult state={done(MARKDOWN)} />)

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
      <EstimationResult state={done('Hecho', { prompt_version: 'v1', cache_hit: true })} />,
      'en',
    )
    expect(screen.getByText('cached')).toBeInTheDocument()

    rerender(<EstimationResult state={done('Hecho')} />)
    expect(screen.queryByText('cached')).not.toBeInTheDocument()
  })

  it('copies the raw Markdown and confirms it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    withLocale(<EstimationResult state={done(MARKDOWN)} />, 'en')

    fireEvent.click(screen.getByRole('button', { name: 'Copy estimate' }))

    expect(writeText).toHaveBeenCalledWith(MARKDOWN)
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('offers no copy button while the estimate is still loading', () => {
    withLocale(<EstimationResult state={loading} />, 'en')
    expect(screen.queryByRole('button', { name: 'Copy estimate' })).not.toBeInTheDocument()
  })

  it('shows errors as an alert', () => {
    withLocale(<ErrorAlert message="Error HTTP 502: El proveedor LLM falló." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Error HTTP 502: El proveedor LLM falló.')
  })
})
