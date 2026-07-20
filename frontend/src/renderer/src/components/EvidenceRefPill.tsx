interface EvidenceRefPillProps {
  evidenceId: string
  onSelect?: (evidenceId: string) => void
}

export function EvidenceRefPill({ evidenceId, onSelect }: EvidenceRefPillProps): JSX.Element {
  return (
    <a
      className="pill evidence-ref-pill"
      href={`#evidence-${evidenceId}`}
      onClick={() => onSelect?.(evidenceId)}
    >
      {evidenceId}
    </a>
  )
}
