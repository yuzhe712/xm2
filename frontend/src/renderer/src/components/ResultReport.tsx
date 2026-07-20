import type { FinalReport } from '../types/tickets'

interface ResultReportProps {
  report?: FinalReport
}

function ListBlock({ title, items }: { title: string; items: string[] }): JSX.Element | null {
  if (items.length === 0) return null
  return (
    <div className="list-block">
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

export function ResultReport({ report }: ResultReportProps): JSX.Element {
  if (!report) {
    return (
      <section className="panel">
        <h2>最终报告</h2>
        <p className="muted">提交工单后在这里展示最终报告。</p>
      </section>
    )
  }

  return (
    <section className="panel report-panel">
      <h2>最终报告</h2>
      <h3 className="report-title">{report.title}</h3>
      <p className="report-summary">{report.summary}</p>
      <ListBlock title="事实" items={report.facts} />
      <ListBlock title="诊断依据摘要" items={report.derived_findings} />
      <ListBlock title="假设" items={report.assumptions} />
      <ListBlock title="未知项" items={report.unknowns} />
      <ListBlock title="建议" items={report.recommendations} />
    </section>
  )
}
