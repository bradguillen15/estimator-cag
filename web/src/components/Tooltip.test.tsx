import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Tooltip } from './Tooltip'

describe('Tooltip', () => {
  it('renders the label as a visual-only hint without changing the trigger name', () => {
    render(
      <Tooltip label="New conversation">
        <button type="button" aria-label="New conversation" />
      </Tooltip>,
    )

    expect(screen.getByRole('button', { name: 'New conversation' })).toBeInTheDocument()
    expect(screen.getByText('New conversation')).toHaveAttribute('aria-hidden', 'true')
  })
})
