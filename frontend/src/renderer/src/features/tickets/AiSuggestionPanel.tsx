import { Bot, RefreshCw, ShieldAlert } from 'lucide-react'
import { useEffect, useState } from 'react'

import type { AiRun } from '../../types/workflow'

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function textValue(value: unknown, fallback = '未提供'): string {
  return typeof value === 'string' && value.trim() ? value : fallback
}

export function AiSuggestionPanel({ run, loading, onRerun, onDecision }: {
  run: AiRun | null
  loading: boolean
  onRerun: () => void
  onDecision: (
    decision: 'accepted' | 'modified' | 'rejected',
    note: string,
    modifiedResult: Record<string, unknown> | null,
  ) => void
}): JSX.Element {
  const result = record(run?.result)
  const triage = record(record(result.triage).classification)
  const diagnosis = record(record(result.retrieve_diagnose).diagnosis)
  const quality = record(result.quality_gate)
  const causes = Array.isArray(diagnosis.candidate_root_causes) ? diagnosis.candidate_root_causes : []
  const evidence = run?.evidence ?? []
  const [decisionNote, setDecisionNote] = useState('')
  const [editedReply, setEditedReply] = useState('')

  useEffect(() => {
    setDecisionNote('')
    setEditedReply(textValue(quality.suggested_reply, ''))
  }, [run?.id, quality.suggested_reply])

  const modifiedResult = (): Record<string, unknown> => ({
    ...(run?.result ?? {}),
    quality_gate: { ...quality, suggested_reply: editedReply.trim() },
  })

  return (
    <aside className="ai-panel" aria-label="AI 辅助建议">
      <div className="section-heading compact-heading">
        <div><Bot size={19} aria-hidden="true" /><h2>AI 辅助建议</h2></div>
        <button className="icon-button" type="button" onClick={onRerun} disabled={loading} aria-label="重新运行 AI" title="重新运行 AI"><RefreshCw size={17} /></button>
      </div>
      {!run && <p className="muted">尚无 AI 运行记录，人工流程仍可继续。</p>}
      {run && (
        <>
          <div className="ai-run-meta"><span className={`run-dot run-${run.status}`} /> <strong>{run.status}</strong><span>{run.stage} · {run.progress}%</span></div>
          {run.status === 'failed' && <div className="inline-alert"><ShieldAlert size={17} /><span>{run.error_message ?? 'AI 分析失败，不影响人工处理。'}</span></div>}
          {run.status === 'completed' && (
            <details className="ai-details" open>
              <summary>查看分析结果</summary>
              <dl className="fact-grid">
                <div><dt>分类</dt><dd>{textValue(triage.category)}</dd></div>
                <div><dt>优先级</dt><dd>{textValue(triage.priority)}</dd></div>
                <div><dt>建议团队</dt><dd>{textValue(quality.recommended_team)}</dd></div>
                <div><dt>置信度</dt><dd>{typeof run.confidence === 'number' ? `${Math.round(run.confidence * 100)}%` : '未提供'}</dd></div>
              </dl>
              <div className="ai-block"><h3>建议回复</h3><textarea aria-label="编辑 AI 建议回复" rows={4} value={editedReply} onChange={(event) => setEditedReply(event.target.value)} /></div>
              <div className="ai-block"><h3>根因候选</h3>{causes.length ? <ol>{causes.slice(0, 3).map((cause, index) => <li key={index}>{textValue(record(cause).cause)}</li>)}</ol> : <p className="muted">未形成可靠根因候选。</p>}</div>
              <div className="ai-block"><h3>证据</h3>{evidence.length ? <ul className="evidence-list">{evidence.slice(0, 6).map((item, index) => <li key={textValue(item.evidence_id, String(index))}><strong>{textValue(item.title ?? item.source_id, `证据 ${index + 1}`)}</strong><span>{textValue(item.summary)}</span></li>)}</ul> : <p className="muted">本次运行没有返回证据。</p>}</div>
              <p className="ai-disclaimer">建议需人工复核后采用。模型：{run.model} · Prompt：{run.prompt_version}</p>
              <div className="ai-decision-controls">
                <label><span>复核备注</span><textarea aria-label="AI 复核备注" rows={2} value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} /></label>
                <div>
                  <button className="button-secondary" type="button" disabled={loading} onClick={() => onDecision('rejected', decisionNote, null)}>拒绝</button>
                  <button className="button-secondary" type="button" disabled={loading || !editedReply.trim()} onClick={() => onDecision('modified', decisionNote, modifiedResult())}>修改后采用</button>
                  <button type="button" disabled={loading} onClick={() => onDecision('accepted', decisionNote, null)}>接受建议</button>
                </div>
              </div>
            </details>
          )}
        </>
      )}
    </aside>
  )
}
