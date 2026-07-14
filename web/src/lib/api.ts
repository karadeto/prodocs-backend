import { clearSession, getToken } from './auth'

// ── Types (mirror backend-py DTOs) ──────────────────────────────

export type DocumentStatus = 'processing' | 'ready' | 'failed'
export type RoutingSource = 'rule' | 'history' | 'llm' | 'fallback' | 'user'

export interface DocumentListItem {
  id: string
  title: string
  status: DocumentStatus
  needs_review: boolean
  routing_source: RoutingSource | null
  routing_reason: string | null
  folder_id: string | null
  original_filename: string
  mime_type: string
  page_count: number | null
  failed_stage: string | null
  error: string | null
  created_at: string
  vendor: string | null
  doc_type: string | null
  doc_date: string | null
  total_gross: number | null
  currency: string | null
}

export interface DocumentFact {
  doc_type: string
  vendor: string | null
  date: string | null
  total_gross: number | null
  currency: string | null
  identifiers: Record<string, string>
  summary: string | null
}

export interface DocumentDetail extends Omit<DocumentListItem, 'vendor' | 'doc_type' | 'doc_date' | 'total_gross' | 'currency'> {
  fact?: DocumentFact
}

export interface FolderNode {
  id: string
  name: string
  code: string | null
  icon: string | null
  is_system: boolean
  document_count: number
  children: FolderNode[]
}

export interface ReviewItem {
  id: string
  title: string
  folder_id: string | null
  routing_source: RoutingSource | null
  routing_reason: string | null
  vendor: string | null
  doc_type: string | null
  created_at: string
}

export interface IngestionEvent {
  stage: string
  status: 'ok' | 'error'
  detail: Record<string, unknown> | null
  error: string | null
  duration_ms: number | null
  at: string
}

export interface ChatThread {
  id: string
  title: string | null
  created_at: string
}

export interface ChatSource {
  document_id: string
  title: string
  page: number | null
}

export interface ChatMessageDto {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: ChatSource[] | null
  created_at: string
}

// ── Fetch wrapper ───────────────────────────────────────────────

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${getToken()}`,
      ...(init?.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...init?.headers,
    },
  })
  if (res.status === 401) {
    clearSession()
    window.location.href = '/login'
    throw new ApiError(401, 'Session expired')
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* keep default */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

// ── Endpoints ───────────────────────────────────────────────────

export const api = {
  listDocuments: (params?: { folderId?: string; status?: string }) => {
    const q = new URLSearchParams()
    if (params?.folderId) q.set('folder_id', params.folderId)
    if (params?.status) q.set('status', params.status)
    const qs = q.toString()
    return request<DocumentListItem[]>(`/documents${qs ? `?${qs}` : ''}`)
  },

  getDocument: (id: string) => request<DocumentDetail>(`/documents/${id}`),

  getDocumentEvents: (id: string) => request<IngestionEvent[]>(`/documents/${id}/events`),

  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentListItem>('/documents', { method: 'POST', body: form })
  },

  reprocessDocument: (id: string) =>
    request<{ status: string }>(`/documents/${id}/reprocess`, { method: 'POST' }),

  documentFileUrl: (id: string) => `/api/v1/documents/${id}/file`,

  getFolders: () => request<FolderNode[]>('/folders'),

  createFolder: (name: string, parentId?: string) =>
    request<{ id: string; name: string }>('/folders', {
      method: 'POST',
      body: JSON.stringify({ name, parent_id: parentId ?? null }),
    }),

  getReviewInbox: () => request<ReviewItem[]>('/review'),

  resolveReview: (documentId: string, action: 'confirm' | 'move', folderId?: string) =>
    request<{ status: string; rule_created: boolean; folder_id: string | null }>(
      `/review/${documentId}`,
      { method: 'POST', body: JSON.stringify({ action, folder_id: folderId ?? null }) },
    ),

  getThreads: () => request<ChatThread[]>('/chat/threads'),

  getThreadMessages: (threadId: string) =>
    request<ChatMessageDto[]>(`/chat/threads/${threadId}/messages`),
}

// ── Folder helpers ──────────────────────────────────────────────

export interface FlatFolder {
  id: string
  name: string
  icon: string | null
  isSystem: boolean
  depth: number
  path: string
  documentCount: number
}

export function flattenFolders(tree: FolderNode[], depth = 0, prefix = ''): FlatFolder[] {
  const out: FlatFolder[] = []
  for (const node of tree) {
    const path = prefix ? `${prefix} / ${node.name}` : node.name
    out.push({
      id: node.id,
      name: node.name,
      icon: node.icon,
      isSystem: node.is_system,
      depth,
      path,
      documentCount: node.document_count,
    })
    out.push(...flattenFolders(node.children, depth + 1, path))
  }
  return out
}

export function totalDocumentCount(tree: FolderNode[]): number {
  return tree.reduce(
    (sum, node) => sum + node.document_count + totalDocumentCount(node.children),
    0,
  )
}
