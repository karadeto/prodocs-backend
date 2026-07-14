/** Brand mark: a binder-register tab. */
export function TabGlyph({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 8.5C3 7.12 4.12 6 5.5 6H9l2 2.5h7.5C19.88 8.5 21 9.62 21 11v5.5c0 1.38-1.12 2.5-2.5 2.5h-13C4.12 19 3 17.88 3 16.5v-8Z"
        fill="var(--color-spine)"
      />
      <path
        d="M3 11h18v5.5c0 1.38-1.12 2.5-2.5 2.5h-13C4.12 19 3 17.88 3 16.5V11Z"
        fill="var(--color-ink)"
      />
    </svg>
  )
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <TabGlyph />
      {!compact && (
        <span className="font-display text-[17px] font-bold tracking-tight text-ink">
          ProDocs
        </span>
      )}
    </span>
  )
}
