import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MockDataBadge } from './MockDataBadge'

describe('MockDataBadge', () => {
  it('shows the mock data label', () => {
    render(<MockDataBadge mode="mock" />)

    expect(screen.getByText('模拟数据 mock')).toBeInTheDocument()
  })
})
