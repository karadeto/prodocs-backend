import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { ArrowLeft, Download, FolderInput, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { FolderPickerDialog } from '@/components/FolderPickerDialog'
import { StatusChip } from '@/components/StatusChip'
import { api, flattenFolders } from '@/lib/api'
import { formatAmount, formatDate, formatDuration, formatRelative } from '@/lib/format'
import { toast } from '@/lib/toast'

export const Route = createFileRoute('/_app/documents/$documentId')({
  component: DocumentPage,
})

const STAGE_LABELS: Record<string, string> = {
  parse: 'Read the document',
  extract: 'Extracted the details',
  facts: 'Saved vendor & amounts',
  route: 'Chose a folder',
  embed: 'Prepared for search',
}

function DocumentPage() {
  const { documentId } = Route.useParams()
  const queryClient = useQueryClient()
  const [moving, setMoving] = useState(false)

  const doc = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => api.getDocument(documentId),
    refetchInterval: (query) => (query.state.data?.status === 'processing' ? 2500 : false),
  })
  const events = useQuery({
    queryKey: ['document-events', documentId],
    queryFn: () => api.getDocumentEvents(documentId),
    refetchInterval: doc.data?.status === 'processing' ? 2500 : false,
  })
  const folders = useQuery({ queryKey: ['folders'], queryFn: api.getFolders })

  const reprocess = useMutation({
    mutationFn: () => api.reprocessDocument(documentId),
    onSuccess: () => {
      toast('Processing again…')
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
    },
  })

  const move = useMutation({
    mutationFn: (folderId: string) => api.resolveReview(documentId, 'move', folderId),
    onSuccess: (result) => {
      toast(result.rule_created ? 'Moved. ProDocs will remember this sender.' : 'Moved.')
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['review'] })
      queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
    onError: (e) => toast(e instanceof Error ? e.message : 'Could not move the document.', 'error'),
  })

  async function download() {
    try {
      const res = await fetch(api.documentFileUrl(documentId), {
        headers: { Authorization: `Bearer ${localStorage.getItem('prodocs.token')}` },
      })
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = doc.data?.original_filename ?? 'document'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast('Download failed. Try again.', 'error')
    }
  }

  if (doc.isLoading) {
    return <div className="mx-auto max-w-4xl px-6 py-8 text-[13px] text-ink-faint">Loading…</div>
  }
  if (!doc.data) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <p className="text-[14px]">This document doesn't exist or was deleted.</p>
        <Link to="/" className="btn-quiet mt-4 inline-flex">
          <ArrowLeft size={14} /> Back to library
        </Link>
      </div>
    )
  }

  const d = doc.data
  const flat = folders.data ? flattenFolders(folders.data) : []
  const folderPath = d.folder_id ? flat.find((f) => f.id === d.folder_id)?.path : undefined

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link to="/" className="mb-5 inline-flex items-center gap-1.5 text-[13px] text-ink-muted hover:text-ink">
        <ArrowLeft size={14} /> Library
      </Link>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1.5 flex items-center gap-2.5">
            <StatusChip status={d.status} needsReview={d.needs_review} />
            <span className="font-mono text-[11.5px] text-ink-faint">
              added {formatRelative(d.created_at)}
              {d.page_count ? `  ·  ${d.page_count} ${d.page_count === 1 ? 'page' : 'pages'}` : ''}
            </span>
          </div>
          <h1 className="font-display text-[22px] leading-tight font-bold tracking-tight break-words">
            {d.title}
          </h1>
        </div>
        <div className="flex shrink-0 gap-2">
          {d.status === 'failed' && (
            <button onClick={() => reprocess.mutate()} disabled={reprocess.isPending} className="btn-quiet">
              <RefreshCw size={14} /> Try again
            </button>
          )}
          <button onClick={() => setMoving(true)} className="btn-quiet">
            <FolderInput size={14} /> Move
          </button>
          <button onClick={download} className="btn-primary">
            <Download size={14} /> Download
          </button>
        </div>
      </header>

      {d.status === 'failed' && d.error && (
        <div className="mb-5 rounded-lg bg-failed-soft px-4 py-3">
          <p className="font-mono text-[11px] tracking-wider text-failed uppercase">
            Failed at: {d.failed_stage ?? 'unknown stage'}
          </p>
          <p className="mt-1 text-[13px] text-failed">{d.error}</p>
        </div>
      )}

      <div className="grid gap-5 md:grid-cols-5">
        {/* Facts */}
        <div className="md:col-span-3">
          <div className="card p-5">
            <p className="eyebrow mb-3">Extracted details</p>
            {d.fact ? (
              <>
                {d.fact.total_gross != null && (
                  <p className="mb-3 font-mono text-[26px] font-medium tracking-tight">
                    {formatAmount(d.fact.total_gross, d.fact.currency)}
                  </p>
                )}
                <dl className="grid grid-cols-[110px_1fr] gap-y-2 text-[13.5px]">
                  <dt className="text-ink-faint">Type</dt>
                  <dd className="font-mono text-[12.5px]">{d.fact.doc_type}</dd>
                  {d.fact.vendor && (
                    <>
                      <dt className="text-ink-faint">From</dt>
                      <dd>{d.fact.vendor}</dd>
                    </>
                  )}
                  {d.fact.date && (
                    <>
                      <dt className="text-ink-faint">Date</dt>
                      <dd className="font-mono text-[12.5px]">{formatDate(d.fact.date)}</dd>
                    </>
                  )}
                  {Object.entries(d.fact.identifiers ?? {}).map(([key, value]) => (
                    <span key={key} className="contents">
                      <dt className="text-ink-faint">{key.replaceAll('_', ' ')}</dt>
                      <dd className="font-mono text-[12.5px] break-all">{value}</dd>
                    </span>
                  ))}
                </dl>
                {d.fact.summary && (
                  <p className="mt-4 border-t border-line pt-3.5 text-[13.5px] text-ink-muted">
                    {d.fact.summary}
                  </p>
                )}
              </>
            ) : (
              <p className="text-[13px] text-ink-faint">
                {d.status === 'processing' ? 'Reading the document…' : 'No details extracted.'}
              </p>
            )}
          </div>

          <div className="card mt-5 p-5">
            <p className="eyebrow mb-2">Filed in</p>
            <p className="font-mono text-[13px]">{folderPath ?? 'Not filed yet'}</p>
            {d.routing_reason && (
              <p className="mt-2 text-[13px] text-ink-muted">{d.routing_reason}</p>
            )}
          </div>
        </div>

        {/* Pipeline audit trail */}
        <div className="md:col-span-2">
          <div className="card p-5">
            <p className="eyebrow mb-3">Processing log</p>
            <ol className="flex flex-col gap-3">
              {events.data?.map((e, i) => (
                <li key={i} className="flex gap-2.5">
                  <span
                    className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                      e.status === 'ok' ? 'bg-filed' : 'bg-failed'
                    }`}
                  />
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium">
                      {STAGE_LABELS[e.stage] ?? e.stage}
                      <span className="ml-2 font-mono text-[11px] font-normal text-ink-faint">
                        {formatDuration(e.duration_ms)}
                      </span>
                    </p>
                    {e.error && <p className="mt-0.5 text-[12px] break-words text-failed">{e.error}</p>}
                  </div>
                </li>
              ))}
              {events.data?.length === 0 && (
                <p className="text-[13px] text-ink-faint">Waiting for the first stage…</p>
              )}
            </ol>
          </div>
        </div>
      </div>

      {moving && (
        <FolderPickerDialog
          title={`Move "${d.title}"`}
          confirmLabel="Move here"
          onClose={() => setMoving(false)}
          onConfirm={(folderId) => {
            move.mutate(folderId)
            setMoving(false)
          }}
        />
      )}
    </div>
  )
}
