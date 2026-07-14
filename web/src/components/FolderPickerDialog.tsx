import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, flattenFolders } from '@/lib/api'

interface Props {
  title: string
  confirmLabel: string
  onConfirm: (folderId: string) => void
  onClose: () => void
}

export function FolderPickerDialog({ title, confirmLabel, onConfirm, onClose }: Props) {
  const folders = useQuery({ queryKey: ['folders'], queryFn: api.getFolders })
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const flat = folders.data ? flattenFolders(folders.data) : []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-ink/30" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="card relative flex max-h-[70vh] w-full max-w-md flex-col shadow-xl"
      >
        <h3 className="font-display border-b border-line px-5 py-3.5 text-[15px] font-semibold">
          {title}
        </h3>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {flat.map((f) => (
            <button
              key={f.id}
              onClick={() => setSelected(f.id)}
              className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13.5px] ${
                selected === f.id
                  ? 'bg-spine-soft text-spine-deep font-medium'
                  : 'text-ink-muted hover:bg-paper hover:text-ink'
              }`}
              style={{ paddingLeft: 10 + f.depth * 16 }}
            >
              {f.icon && <span className="leading-none">{f.icon}</span>}
              <span className="truncate">{f.name}</span>
            </button>
          ))}
          {flat.length === 0 && (
            <p className="px-3 py-6 text-center text-[13px] text-ink-faint">Loading folders…</p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-line px-4 py-3">
          <button onClick={onClose} className="btn-quiet">
            Cancel
          </button>
          <button
            disabled={!selected}
            onClick={() => selected && onConfirm(selected)}
            className="btn-primary"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
