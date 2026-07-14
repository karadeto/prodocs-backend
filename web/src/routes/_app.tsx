import { useQuery } from '@tanstack/react-query'
import { Link, Outlet, createFileRoute, redirect, useNavigate } from '@tanstack/react-router'
import { ChevronRight, FolderOpen, Inbox, LogOut, Menu, MessageSquareText, X } from 'lucide-react'
import { useState } from 'react'
import { Wordmark } from '@/components/Logo'
import { api, totalDocumentCount, type FolderNode } from '@/lib/api'
import { clearSession, getEmail, isAuthenticated } from '@/lib/auth'

export const Route = createFileRoute('/_app')({
  beforeLoad: () => {
    if (!isAuthenticated()) throw redirect({ to: '/login' })
  },
  component: AppShell,
})

function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  return (
    <div className="flex h-full">
      {/* Desktop sidebar */}
      <aside className="hidden w-[264px] shrink-0 border-r border-line lg:flex">
        <Sidebar onNavigate={() => {}} />
      </aside>

      {/* Mobile off-canvas */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-ink/30"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 flex w-[280px] border-r border-line bg-paper shadow-xl">
            <Sidebar onNavigate={() => setMobileOpen(false)} />
            <button
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
              className="absolute top-3 right-3 rounded-md p-1 text-ink-muted hover:text-ink"
            >
              <X size={18} />
            </button>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="flex items-center gap-3 border-b border-line bg-paper px-4 py-2.5 lg:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            className="rounded-md p-1 text-ink-muted hover:text-ink"
          >
            <Menu size={20} />
          </button>
          <Wordmark />
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto bg-surface">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const navigate = useNavigate()
  const folders = useQuery({ queryKey: ['folders'], queryFn: api.getFolders })
  const review = useQuery({ queryKey: ['review'], queryFn: api.getReviewInbox })
  const reviewCount = review.data?.length ?? 0
  const allCount = folders.data ? totalDocumentCount(folders.data) : 0

  function signOut() {
    clearSession()
    navigate({ to: '/login' })
  }

  return (
    <nav className="flex h-full w-full flex-col bg-paper">
      <div className="px-4 pt-5 pb-4">
        <Link to="/" onClick={onNavigate}>
          <Wordmark />
        </Link>
      </div>

      {/* Primary nav — register tabs */}
      <div className="flex flex-col gap-0.5 pl-3">
        <TabLink to="/" exact onNavigate={onNavigate} icon={<FolderOpen size={16} />}>
          Library
          {allCount > 0 && <Count>{allCount}</Count>}
        </TabLink>
        <TabLink to="/review" onNavigate={onNavigate} icon={<Inbox size={16} />}>
          Review
          {reviewCount > 0 && (
            <span className="ml-auto rounded-full bg-review-soft px-1.5 py-px font-mono text-[10.5px] font-semibold text-review">
              {reviewCount}
            </span>
          )}
        </TabLink>
        <TabLink to="/chat" onNavigate={onNavigate} icon={<MessageSquareText size={16} />}>
          Ask
        </TabLink>
      </div>

      {/* Folder tree */}
      <div className="mt-6 min-h-0 flex-1 overflow-y-auto pb-4 pl-3">
        <p className="eyebrow mb-2 pl-2.5">Folders</p>
        {folders.data?.map((node) => (
          <FolderTreeItem key={node.id} node={node} depth={0} onNavigate={onNavigate} />
        ))}
      </div>

      <div className="border-t border-line px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-[12.5px] text-ink-muted">{getEmail()}</span>
          <button
            onClick={signOut}
            title="Sign out"
            aria-label="Sign out"
            className="rounded-md p-1.5 text-ink-faint hover:bg-line/60 hover:text-ink"
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </nav>
  )
}

function TabLink({
  to,
  exact,
  icon,
  children,
  onNavigate,
}: {
  to: string
  exact?: boolean
  icon: React.ReactNode
  children: React.ReactNode
  onNavigate: () => void
}) {
  return (
    <Link
      to={to}
      onClick={onNavigate}
      activeOptions={{ exact, includeSearch: false }}
      className="flex items-center gap-2.5 rounded-l-lg py-2 pr-3 pl-3 text-[13.5px] font-medium text-ink-muted hover:text-ink"
      activeProps={{
        className:
          'bg-surface text-ink shadow-[inset_3px_0_0_var(--color-spine)] border-y border-l border-line -mr-px',
      }}
    >
      {icon}
      {children}
    </Link>
  )
}

function Count({ children }: { children: React.ReactNode }) {
  return <span className="ml-auto font-mono text-[11px] text-ink-faint">{children}</span>
}

function subtreeCount(node: FolderNode): number {
  return node.document_count + node.children.reduce((s, c) => s + subtreeCount(c), 0)
}

function FolderTreeItem({
  node,
  depth,
  onNavigate,
}: {
  node: FolderNode
  depth: number
  onNavigate: () => void
}) {
  const [open, setOpen] = useState(false)
  const count = subtreeCount(node)
  const hasChildren = node.children.length > 0

  return (
    <div>
      <div className="flex items-center">
        {hasChildren ? (
          <button
            onClick={() => setOpen(!open)}
            aria-label={open ? `Collapse ${node.name}` : `Expand ${node.name}`}
            className="shrink-0 rounded p-0.5 text-ink-faint hover:text-ink"
            style={{ marginLeft: depth * 14 }}
          >
            <ChevronRight size={13} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
          </button>
        ) : (
          <span style={{ marginLeft: depth * 14 + 18 }} />
        )}
        <Link
          to="/"
          search={{ folder: node.id }}
          onClick={onNavigate}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-l-lg py-1.5 pr-3 pl-1.5 text-[13px] text-ink-muted hover:text-ink"
          activeProps={{
            className:
              'bg-surface text-ink font-medium shadow-[inset_3px_0_0_var(--color-spine)]',
          }}
          activeOptions={{ exact: true, includeSearch: true }}
        >
          {node.icon && <span className="text-[13px] leading-none">{node.icon}</span>}
          <span className="truncate">{node.name}</span>
          {count > 0 && <Count>{count}</Count>}
        </Link>
      </div>
      {open &&
        node.children.map((child) => (
          <FolderTreeItem key={child.id} node={child} depth={depth + 1} onNavigate={onNavigate} />
        ))}
    </div>
  )
}
