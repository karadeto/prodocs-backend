import { getToken } from './auth'
import type { ChatSource } from './api'

export interface StreamHandlers {
  onThread?: (threadId: string) => void
  onToken: (text: string) => void
  onSources?: (sources: ChatSource[]) => void
  onError?: (message: string) => void
  onDone?: () => void
}

/** POST-based SSE reader (EventSource can't send a body). */
export async function streamChat(
  message: string,
  threadId: string | null,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${getToken()}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  })
  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed (${res.status})`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = (block: string) => {
    let event = 'message'
    const dataLines: string[] = []
    for (const rawLine of block.split(/\r?\n/)) {
      if (rawLine.startsWith('event:')) event = rawLine.slice(6).trim()
      else if (rawLine.startsWith('data:')) dataLines.push(rawLine.slice(5).trimStart())
    }
    if (dataLines.length === 0) return
    let data: any
    try {
      data = JSON.parse(dataLines.join('\n'))
    } catch {
      return
    }
    switch (event) {
      case 'thread':
        handlers.onThread?.(data.thread_id)
        break
      case 'token':
        handlers.onToken(data.text)
        break
      case 'sources':
        handlers.onSources?.(data.sources ?? [])
        break
      case 'error':
        handlers.onError?.(data.error ?? 'The assistant ran into a problem.')
        break
      case 'done':
        handlers.onDone?.()
        break
    }
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) dispatch(block)
  }
  if (buffer.trim()) dispatch(buffer)
}
