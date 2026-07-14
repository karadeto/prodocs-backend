import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { Check, CheckCircle2, FolderInput } from 'lucide-react'
import { useState } from 'react'
import { FolderPickerDialog } from '@/components/FolderPickerDialog'
import { api, flattenFolders, type ReviewItem } from '@/lib/api'
import { formatRelative } from '@/lib/format'
import { toast } from '@/lib/toast'

export const Route = createFileRoute('/_app/review')({
  component: ReviewPage,
})

function ReviewPage() {
  const queryClient = useQueryClient()
  const review = useQuery({ queryKey: ['review'], queryFn: api.getReviewInbox })
  const folders = useQuery({ queryKey: ['folders'], queryFn: api.getFolders })
  const [moving, setMoving] = useState<ReviewItem | null>(null)

  const flat = folders.data ? flattenFolders(folders.data) : []
  const pathOf = (folderId: string | null) =>
    folderId ? (flat.find((f) => f.id === folderId)?.path ?? '—') : '—'

  const resolve = useMutation({
    mutationFn: ({ item, action, folderId }: { item: ReviewItem; action: 'confirm' | 'move'; folderId?: string }) =>
      api.resolveReview(item.id, action, folderId),
    onSuccess: (result, { item }) => {
      toast(
        result.rule_created && item.vendor
          ? `Filed. ${item.vendor} will file automatically from now on.`
          : 'Filed.',
      )
      queryClient.invalidateQueries({ queryKey: ['review'] })
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
    onError: (e) => toast(e instanceof Error ? e.message : 'Could not update the document.', 'error'),
  })

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <header className="mb-6">
        <p className="eyebrow mb-1">Review</p>
        <h1 className="font-display text-[22px] leading-tight font-bold tracking-tight">
          Confirm the filing
        </h1>
        <p className="mt-1.5 max-w-lg text-[13.5px] text-ink-muted">
          These documents were filed by AI. Confirming teaches ProDocs — the same sender is filed
          automatically next time.
        </p>
      </header>

      {review.data && review.data.length === 0 && (
        <div className="flex flex-col items-center rounded-xl border border-line px-6 py-16 text-center">
          <CheckCircle2 size={28} className="mb-3 text-filed" />
          <p className="font-display text-[16px] font-semibold">Inbox clear</p>
          <p className="mt-1 text-[13px] text-ink-muted">Everything is filed and confirmed.</p>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {review.data?.map((item) => (
          <div key={item.id} className="card p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: item.id }}
                  className="text-[14.5px] font-medium hover:underline"
                >
                  {item.title}
                </Link>
                <p className="mt-0.5 font-mono text-[11.5px] text-ink-faint">
                  {[item.vendor, item.doc_type, formatRelative(item.created_at)]
                    .filter(Boolean)
                    .join('  ·  ')}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => setMoving(item)}
                  disabled={resolve.isPending}
                  className="btn-quiet"
                >
                  <FolderInput size={14} />
                  Move to…
                </button>
                <button
                  onClick={() => resolve.mutate({ item, action: 'confirm' })}
                  disabled={resolve.isPending}
                  className="btn-primary"
                >
                  <Check size={14} />
                  Looks right
                </button>
              </div>
            </div>

            <div className="mt-3 rounded-lg bg-paper px-3 py-2.5">
              <p className="font-mono text-[12px] text-ink">
                <span className="text-ink-faint">Filed in&nbsp;&nbsp;</span>
                {pathOf(item.folder_id)}
              </p>
              {item.routing_reason && (
                <p className="mt-1 text-[12.5px] text-ink-muted">{item.routing_reason}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {moving && (
        <FolderPickerDialog
          title={`Move "${moving.title}"`}
          confirmLabel="Move here"
          onClose={() => setMoving(null)}
          onConfirm={(folderId) => {
            resolve.mutate({ item: moving, action: 'move', folderId })
            setMoving(null)
          }}
        />
      )}
    </div>
  )
}
