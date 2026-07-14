import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { FileText, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { StatusChip } from '@/components/StatusChip'
import { api, flattenFolders } from '@/lib/api'
import { formatAmount, formatDate, formatRelative } from '@/lib/format'
import { toast } from '@/lib/toast'

export const Route = createFileRoute('/_app/')({
  validateSearch: (search: Record<string, unknown>): { folder?: string } => ({
    folder: typeof search.folder === 'string' ? search.folder : undefined,
  }),
  component: LibraryPage,
})

function LibraryPage() {
  const { folder } = Route.useSearch()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const folders = useQuery({ queryKey: ['folders'], queryFn: api.getFolders })
  const documents = useQuery({
    queryKey: ['documents', folder ?? 'all'],
    queryFn: () => api.listDocuments(folder ? { folderId: folder } : undefined),
    refetchInterval: (query) =>
      query.state.data?.some((d) => d.status === 'processing') ? 2500 : false,
  })

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDocument(file),
    onSuccess: (doc) => {
      toast(`"${doc.original_filename}" uploaded — filing it now.`)
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (e) => toast(e instanceof Error ? e.message : 'Upload failed.', 'error'),
  })

  const flat = folders.data ? flattenFolders(folders.data) : []
  const currentFolder = folder ? flat.find((f) => f.id === folder) : undefined

  function handleFiles(files: FileList | null) {
    if (!files) return
    for (const file of files) upload.mutate(file)
  }

  return (
    <div
      className="relative min-h-full"
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={(e) => {
        if (e.currentTarget.contains(e.relatedTarget as Node)) return
        setDragging(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        handleFiles(e.dataTransfer.files)
      }}
    >
      {dragging && (
        <div className="pointer-events-none absolute inset-3 z-30 flex items-center justify-center rounded-xl border-2 border-dashed border-spine bg-spine-soft/80">
          <p className="font-display text-[17px] font-semibold text-spine-deep">
            Drop to upload — it files itself
          </p>
        </div>
      )}

      <div className="mx-auto max-w-4xl px-6 py-8">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow mb-1">{currentFolder ? 'Folder' : 'Library'}</p>
            <h1 className="font-display text-[22px] leading-tight font-bold tracking-tight">
              {currentFolder ? currentFolder.path : 'All documents'}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            {folder && (
              <Link to="/" className="btn-quiet">
                All documents
              </Link>
            )}
            <button onClick={() => fileInput.current?.click()} className="btn-primary">
              <Upload size={15} />
              Upload
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,image/png,image/jpeg,image/tiff,image/webp"
              multiple
              hidden
              onChange={(e) => {
                handleFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </div>
        </header>

        {documents.data && documents.data.length === 0 && (
          <button
            onClick={() => fileInput.current?.click()}
            className="flex w-full flex-col items-center rounded-xl border-2 border-dashed border-line-strong px-6 py-16 text-center hover:border-spine hover:bg-spine-soft/40"
          >
            <FileText size={28} className="mb-3 text-ink-faint" />
            <p className="font-display text-[16px] font-semibold">
              {currentFolder ? 'Nothing filed here yet' : 'Drop a PDF here — it files itself'}
            </p>
            <p className="mt-1 text-[13px] text-ink-muted">
              PDF, PNG or JPEG · vendor, date and amount are extracted automatically
            </p>
          </button>
        )}

        {documents.data && documents.data.length > 0 && (
          <div className="card divide-y divide-line">
            {documents.data.map((doc) => (
              <Link
                key={doc.id}
                to="/documents/$documentId"
                params={{ documentId: doc.id }}
                className="flex items-center gap-4 px-4 py-3 hover:bg-paper/60"
              >
                <FileText size={18} className="shrink-0 text-ink-faint" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-medium">{doc.title}</p>
                  <p className="mt-0.5 truncate font-mono text-[11.5px] text-ink-faint">
                    {[doc.vendor, formatDate(doc.doc_date) || formatRelative(doc.created_at)]
                      .filter(Boolean)
                      .join('  ·  ')}
                  </p>
                </div>
                {doc.total_gross != null && (
                  <span className="shrink-0 font-mono text-[13px] font-medium text-ink">
                    {formatAmount(doc.total_gross, doc.currency)}
                  </span>
                )}
                <StatusChip status={doc.status} needsReview={doc.needs_review} />
              </Link>
            ))}
          </div>
        )}

        {documents.isLoading && (
          <div className="card divide-y divide-line">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-4">
                <div className="h-4 w-4 rounded bg-line" />
                <div className="h-3.5 w-1/2 rounded bg-line" />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
