import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { BackendConnectionPanel } from './BackendConnectionPanel'

describe('BackendConnectionPanel', () => {
  it('applies a valid backend URL', () => {
    const onChange = vi.fn()
    render(
      <BackendConnectionPanel
        defaultUrl="http://127.0.0.1:8000"
        value="http://127.0.0.1:8000"
        onChange={onChange}
      />,
    )

    fireEvent.change(screen.getByLabelText('后端地址'), {
      target: { value: 'http://ops-workbench.internal:8000/' },
    })
    fireEvent.click(screen.getByText('应用地址'))

    expect(onChange).toHaveBeenCalledWith('http://ops-workbench.internal:8000')
  })

  it('rejects invalid backend URLs and can reset to default', () => {
    const onChange = vi.fn()
    render(
      <BackendConnectionPanel
        defaultUrl="http://127.0.0.1:8000"
        value="http://127.0.0.1:8000"
        onChange={onChange}
      />,
    )

    fireEvent.change(screen.getByLabelText('后端地址'), { target: { value: 'not-a-url' } })
    fireEvent.click(screen.getByText('应用地址'))

    expect(screen.getByText('后端地址无效，请输入完整的 http(s) 地址。')).toBeInTheDocument()

    fireEvent.click(screen.getByText('恢复默认'))

    expect(onChange).toHaveBeenCalledWith('http://127.0.0.1:8000')
  })
})
