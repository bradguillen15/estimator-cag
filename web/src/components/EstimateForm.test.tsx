import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { pdf } from '../test/fixtures'
import { withLocale } from '../test/render'
import { EstimateForm } from './EstimateForm'

const DESCRIPTION = 'Portal interno para reservar salas de reuniones.'

function setup(busy = false, locale: 'es' | 'en' = 'es') {
  const onSubmit = vi.fn()
  const user = userEvent.setup()
  withLocale(<EstimateForm busy={busy} onSubmit={onSubmit} />, locale)
  return {
    onSubmit,
    user,
    description: screen.getByLabelText(
      locale === 'es' ? /transcripción o descripción del proyecto/i : /transcript or project description/i,
    ),
    submit: screen.getByRole('button', {
      name: locale === 'es' ? /generar estimación|generando/i : /generate estimate|generating/i,
    }),
  }
}

describe('EstimateForm', () => {
  it('keeps submit disabled until the description reaches 20 characters', async () => {
    const { user, description, submit } = setup()
    expect(submit).toBeDisabled()

    await user.type(description, 'Muy corto')
    expect(screen.getByText(/9 \/ 20000/)).toBeInTheDocument()
    expect(screen.getByText(/mínimo 20/)).toBeInTheDocument()
    expect(submit).toBeDisabled()

    await user.type(description, ' pero ahora ya alcanza')
    expect(submit).toBeEnabled()
    expect(screen.queryByText(/mínimo 20/)).not.toBeInTheDocument()
  })

  it('ignores surrounding whitespace when counting', async () => {
    const { user, description, submit } = setup()
    await user.type(description, `   ${'x'.repeat(19)}   `)
    expect(submit).toBeDisabled()
  })

  it('submits the trimmed description with the default options', async () => {
    const { user, description, submit, onSubmit } = setup()

    await user.type(description, `  ${DESCRIPTION}  `)
    await user.click(submit)

    expect(onSubmit).toHaveBeenCalledWith(
      {
        description: DESCRIPTION,
        project_type: 'mobile_app',
        detail_level: 'medium',
        output_format: 'phases_table',
      },
      [],
    )
  })

  it('submits the options the user picked', async () => {
    const { user, description, submit, onSubmit } = setup()

    await user.type(description, DESCRIPTION)
    await user.selectOptions(screen.getByLabelText('Tipo de proyecto'), 'Pipeline de datos')
    await user.selectOptions(screen.getByLabelText('Nivel de detalle'), 'Detallado')
    await user.selectOptions(screen.getByLabelText('Formato de salida'), 'Narrativo')
    await user.click(submit)

    expect(onSubmit).toHaveBeenCalledWith(
      {
        description: DESCRIPTION,
        project_type: 'data_pipeline',
        detail_level: 'detailed',
        output_format: 'narrative',
      },
      [],
    )
  })

  it('shows English labels when the locale is English', async () => {
    const { user, description, submit, onSubmit } = setup(false, 'en')

    expect(screen.getByLabelText('Project type')).toBeInTheDocument()
    await user.type(description, DESCRIPTION)
    await user.selectOptions(screen.getByLabelText('Project type'), 'Data pipeline')
    await user.click(submit)

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ project_type: 'data_pipeline' }),
      [],
    )
    expect(submit).toHaveTextContent('Generate estimate')
  })

  it('submits with Cmd/Ctrl+Enter from the description', async () => {
    const { user, description, onSubmit } = setup()

    await user.type(description, DESCRIPTION)
    await user.keyboard('{Meta>}{Enter}{/Meta}')
    await user.keyboard('{Control>}{Enter}{/Control}')

    expect(onSubmit).toHaveBeenCalledTimes(2)
  })

  it('does not submit an invalid description with the shortcut', async () => {
    const { user, description, onSubmit } = setup()
    await user.type(description, 'corto{Meta>}{Enter}{/Meta}')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('shows progress and blocks resubmission while busy', async () => {
    const { user, description, submit, onSubmit } = setup(true)

    await user.type(description, `${DESCRIPTION}{Meta>}{Enter}{/Meta}`)

    expect(submit).toHaveTextContent('Generando…')
    expect(submit).toBeDisabled()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('passes the selected files on submit and lets the user remove one', async () => {
    const { user, description, submit, onSubmit } = setup()
    const a = pdf('a.pdf')
    const b = pdf('b.pdf')

    await user.type(description, DESCRIPTION)
    await user.upload(screen.getByLabelText(/adjuntos/i), [a, b])
    expect(screen.getByText('a.pdf')).toBeInTheDocument()
    expect(screen.getByText('b.pdf')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Quitar a.pdf' }))
    expect(screen.queryByText('a.pdf')).not.toBeInTheDocument()

    await user.click(submit)
    expect(onSubmit).toHaveBeenCalledWith(expect.any(Object), [b])
  })

  it('accepts only PDF and Word files in the picker', () => {
    setup()
    const input = screen.getByLabelText(/adjuntos/i)
    expect(input).toHaveAttribute('accept', '.pdf,.docx')
    expect(input).toHaveAttribute('multiple')
  })

  it('caps the attachments at 5 and shows a hint', async () => {
    const { user, description, submit, onSubmit } = setup()
    const files = Array.from({ length: 7 }, (_, index) => pdf(`f${index}.pdf`))

    await user.type(description, DESCRIPTION)
    await user.upload(screen.getByLabelText(/adjuntos/i), files)

    expect(screen.getAllByRole('button', { name: /^Quitar / })).toHaveLength(5)
    expect(screen.queryByText('f5.pdf')).not.toBeInTheDocument()
    expect(screen.getByText(/Máximo 5 archivos/)).toBeInTheDocument()

    await user.click(submit)
    expect(onSubmit).toHaveBeenCalledWith(expect.any(Object), files.slice(0, 5))
  })
})
