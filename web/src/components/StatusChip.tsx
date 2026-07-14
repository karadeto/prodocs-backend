import type { DocumentStatus } from '@/lib/api'

interface Props {
  status: DocumentStatus
  needsReview: boolean
}

const styles: Record<string, { label: string; cls: string; pulse?: boolean }> = {
  processing: { label: 'Filing', cls: 'bg-processing-soft text-processing', pulse: true },
  review: { label: 'Review', cls: 'bg-review-soft text-review' },
  filed: { label: 'Filed', cls: 'bg-filed-soft text-filed' },
  failed: { label: 'Failed', cls: 'bg-failed-soft text-failed' },
}

export function StatusChip({ status, needsReview }: Props) {
  const key =
    status === 'processing' ? 'processing'
    : status === 'failed' ? 'failed'
    : needsReview ? 'review'
    : 'filed'
  const s = styles[key]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[10.5px] font-medium tracking-wider uppercase ${s.cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full bg-current ${s.pulse ? 'pulse-dot' : ''}`} />
      {s.label}
    </span>
  )
}
