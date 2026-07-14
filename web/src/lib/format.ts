const eur = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' })

export function formatAmount(value: number | null | undefined, currency?: string | null): string {
  if (value == null) return ''
  if (!currency || currency === 'EUR') return eur.format(value)
  try {
    return new Intl.NumberFormat('de-DE', { style: 'currency', currency }).format(value)
  } catch {
    return `${value.toFixed(2)} ${currency}`
  }
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export function formatRelative(iso: string): string {
  const d = new Date(iso)
  const diffMs = Date.now() - d.getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} d ago`
  return formatDate(iso)
}

export function formatDuration(ms: number | null): string {
  if (ms == null) return ''
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}
