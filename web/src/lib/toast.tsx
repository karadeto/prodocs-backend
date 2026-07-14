import { useEffect, useState } from 'react'

type Tone = 'default' | 'error'
interface ToastItem {
  id: number
  message: string
  tone: Tone
}

let nextId = 1
let items: ToastItem[] = []
const listeners = new Set<(items: ToastItem[]) => void>()

function emit() {
  for (const l of listeners) l([...items])
}

export function toast(message: string, tone: Tone = 'default') {
  const item = { id: nextId++, message, tone }
  items = [...items, item]
  emit()
  setTimeout(() => {
    items = items.filter((t) => t.id !== item.id)
    emit()
  }, 4500)
}

export function Toasts() {
  const [list, setList] = useState<ToastItem[]>([])
  useEffect(() => {
    listeners.add(setList)
    return () => {
      listeners.delete(setList)
    }
  }, [])
  if (list.length === 0) return null
  return (
    <div className="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2">
      {list.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`rounded-lg px-4 py-2.5 text-[13.5px] font-medium shadow-lg ${
            t.tone === 'error' ? 'bg-failed text-white' : 'bg-ink text-white'
          }`}
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}
