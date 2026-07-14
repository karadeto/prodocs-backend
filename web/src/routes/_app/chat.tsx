import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { ArrowUp, FileText, Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { api, type ChatSource } from '@/lib/api'
import { streamChat } from '@/lib/sse'
import { toast } from '@/lib/toast'

export const Route = createFileRoute('/_app/chat')({
  component: ChatPage,
})

interface LocalMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  streaming?: boolean
}

const STARTERS = [
  'How much did I spend at Amazon this year?',
  'When does my rental contract end?',
  'List my insurance policies',
  'What was my last electricity bill?',
]

function ChatPage() {
  const queryClient = useQueryClient()
  const [threadId, setThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<LocalMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const threads = useQuery({ queryKey: ['threads'], queryFn: api.getThreads })

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  async function openThread(id: string) {
    setThreadId(id)
    setBusy(false)
    try {
      const msgs = await queryClient.fetchQuery({
        queryKey: ['thread-messages', id],
        queryFn: () => api.getThreadMessages(id),
      })
      setMessages(
        msgs.map((m) => ({ role: m.role, content: m.content, sources: m.sources ?? undefined })),
      )
    } catch {
      toast('Could not load this conversation.', 'error')
    }
  }

  function newChat() {
    setThreadId(null)
    setMessages([])
    setInput('')
  }

  async function send(text: string) {
    const message = text.trim()
    if (!message || busy) return
    setInput('')
    setBusy(true)
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: message },
      { role: 'assistant', content: '', streaming: true },
    ])

    const patchLast = (patch: Partial<LocalMessage>) =>
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = { ...next[next.length - 1], ...patch }
        return next
      })

    try {
      await streamChat(message, threadId, {
        onThread: (id) => setThreadId(id),
        onToken: (t) =>
          setMessages((prev) => {
            const next = [...prev]
            const last = next[next.length - 1]
            next[next.length - 1] = { ...last, content: last.content + t }
            return next
          }),
        onSources: (sources) => patchLast({ sources }),
        onError: (msg) => patchLast({ content: `Something went wrong: ${msg}`, streaming: false }),
        onDone: () => {
          patchLast({ streaming: false })
          queryClient.invalidateQueries({ queryKey: ['threads'] })
        },
      })
    } catch {
      patchLast({
        content: 'The assistant is unreachable right now. Check that the backend is running.',
        streaming: false,
      })
    } finally {
      patchLast({ streaming: false })
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full">
      {/* Threads rail */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line md:flex">
        <div className="p-3">
          <button onClick={newChat} className="btn-quiet w-full justify-center">
            <Plus size={14} /> New question
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          <p className="eyebrow mb-2 px-1">Recent</p>
          {threads.data?.map((t) => (
            <button
              key={t.id}
              onClick={() => openThread(t.id)}
              className={`w-full truncate rounded-md px-2.5 py-1.5 text-left text-[13px] ${
                t.id === threadId
                  ? 'bg-paper font-medium text-ink shadow-[inset_3px_0_0_var(--color-spine)]'
                  : 'text-ink-muted hover:bg-paper hover:text-ink'
              }`}
            >
              {t.title ?? 'Untitled'}
            </button>
          ))}
          {threads.data?.length === 0 && (
            <p className="px-1 text-[12.5px] text-ink-faint">No conversations yet.</p>
          )}
        </div>
      </aside>

      {/* Conversation */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-2xl px-5 py-8">
            {messages.length === 0 && (
              <div className="pt-16 text-center">
                <p className="eyebrow mb-2">Ask</p>
                <h1 className="font-display text-[22px] font-bold tracking-tight">
                  Ask your documents anything
                </h1>
                <p className="mx-auto mt-2 max-w-sm text-[13.5px] text-ink-muted">
                  Answers come from your own files, with the sources cited.
                </p>
                <div className="mx-auto mt-8 flex max-w-md flex-col gap-2">
                  {STARTERS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="rounded-lg border border-line bg-surface px-4 py-2.5 text-left text-[13.5px] text-ink-muted hover:border-spine hover:text-ink"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-col gap-5">
              {messages.map((m, i) =>
                m.role === 'user' ? (
                  <div key={i} className="self-end">
                    <div className="max-w-md rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[14px] text-white">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="max-w-full self-start">
                    <div className="chat-prose text-[14px]">
                      <Markdown>{m.content}</Markdown>
                      {m.streaming && <span className="stream-cursor text-spine-deep">▍</span>}
                    </div>
                    {m.sources && m.sources.length > 0 && (
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        {m.sources.map((s, j) => (
                          <Link
                            key={j}
                            to="/documents/$documentId"
                            params={{ documentId: s.document_id }}
                            className="inline-flex max-w-60 items-center gap-1.5 rounded-full border border-line bg-paper px-2.5 py-1 font-mono text-[11px] text-ink-muted hover:border-spine hover:text-ink"
                          >
                            <FileText size={11} className="shrink-0" />
                            <span className="truncate">{s.title}</span>
                            {s.page != null && <span className="text-ink-faint">p.{s.page}</span>}
                          </Link>
                        ))}
                      </div>
                    )}
                  </div>
                ),
              )}
            </div>
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-line bg-surface px-5 py-4">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              send(input)
            }}
            className="mx-auto flex max-w-2xl items-end gap-2"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send(input)
                }
              }}
              rows={1}
              placeholder="Ask about your documents…"
              className="max-h-40 min-h-[42px] flex-1 resize-y rounded-xl border border-line-strong bg-surface px-3.5 py-2.5 text-[14px] placeholder:text-ink-faint"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              aria-label="Send"
              className="btn-primary h-[42px] w-[42px] justify-center rounded-xl p-0"
            >
              <ArrowUp size={17} />
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
