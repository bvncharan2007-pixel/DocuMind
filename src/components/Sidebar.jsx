import React, { useState } from 'react';
import {
  Plus, MessageSquare, FileText, Trash2,
  PencilLine, Check, X, Loader2, ChevronLeft, ChevronRight,
  AlertCircle,
} from 'lucide-react';

/**
 * Conversation-history sidebar.
 * Receives real data from App via props — no fetch calls here.
 */
export default function Sidebar({
  conversations,
  activeConvId,
  onSelectConversation,
  onCreateConversation,
  onRenameConversation,
  onDeleteConversation,
  isOpen,
  onToggle,
  loading,
}) {
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const startRename = (conv, e) => {
    e.stopPropagation();
    setRenamingId(conv.id);
    setRenameValue(conv.title);
    setConfirmDeleteId(null);
  };

  const commitRename = async (convId, e) => {
    e?.stopPropagation();
    if (!renameValue.trim()) { cancelRename(); return; }
    await onRenameConversation(convId, renameValue.trim());
    setRenamingId(null);
  };

  const cancelRename = () => { setRenamingId(null); setRenameValue(''); };

  const askDelete = (convId, e) => {
    e.stopPropagation();
    setConfirmDeleteId(convId);
    setRenamingId(null);
  };

  const confirmDelete = async (convId, e) => {
    e.stopPropagation();
    setDeletingId(convId);
    try { await onDeleteConversation(convId); }
    finally { setDeletingId(null); setConfirmDeleteId(null); }
  };

  const cancelDelete = (e) => { e.stopPropagation(); setConfirmDeleteId(null); };

  const formatDate = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = now - d;
    if (diff < 60_000)  return 'Just now';
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  return (
    <aside style={{
      width: isOpen ? 'var(--sidebar-width)' : '52px',
      minWidth: isOpen ? 'var(--sidebar-width)' : '52px',
      transition: 'width var(--transition-normal), min-width var(--transition-normal)',
      background: 'var(--bg-secondary)',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflow: 'hidden',
      position: 'relative',
      zIndex: 20,
      flexShrink: 0,
    }}>
      {/* ── Header row ── */}
      <div style={{
        padding: isOpen ? '14px 14px 10px' : '14px 0 10px',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: isOpen ? 'space-between' : 'center',
        gap: '8px',
        flexShrink: 0,
      }}>
        {isOpen && (
          <span style={{
            fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '0.06em', color: 'var(--text-muted)',
          }}>
            Conversations
          </span>
        )}
        <button
          onClick={onToggle}
          title={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          style={{
            width: '26px', height: '26px', borderRadius: 'var(--radius-sm)',
            background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', color: 'var(--text-muted)', flexShrink: 0,
          }}
          aria-label={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {isOpen ? <ChevronLeft size={13} /> : <ChevronRight size={13} />}
        </button>
      </div>

      {/* ── New conversation button ── */}
      <div style={{ padding: isOpen ? '10px 12px' : '10px 8px', flexShrink: 0 }}>
        <button
          onClick={onCreateConversation}
          title="New conversation"
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: isOpen ? 'flex-start' : 'center',
            gap: '8px',
            padding: isOpen ? '8px 12px' : '8px',
            background: 'var(--accent-muted)',
            border: '1px dashed var(--accent-primary)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--accent-primary)',
            fontSize: '13px',
            fontWeight: 500,
            cursor: 'pointer',
            transition: 'all var(--transition-fast)',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'rgba(13,148,136,0.2)';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'var(--accent-muted)';
          }}
          aria-label="New conversation"
        >
          <Plus size={15} />
          {isOpen && <span>New conversation</span>}
        </button>
      </div>

      {/* ── Conversation list ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: isOpen ? '0 8px 12px' : '0 6px 12px' }}>
        {loading && conversations.length === 0 && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '24px 0' }}>
            <Loader2 size={18} className="animate-spin-slow" color="var(--text-muted)" />
          </div>
        )}

        {!loading && conversations.length === 0 && isOpen && (
          <div style={{
            textAlign: 'center', padding: '32px 16px',
            color: 'var(--text-muted)', fontSize: '12px', lineHeight: 1.6,
          }}>
            <MessageSquare size={28} color="var(--border-medium)" style={{ margin: '0 auto 12px' }} />
            <p style={{ fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}>
              No conversations yet
            </p>
            <p>Click "New conversation" to start chatting with your PDFs.</p>
          </div>
        )}

        {conversations.map(conv => {
          const isActive = conv.id === activeConvId;
          const isRenaming = renamingId === conv.id;
          const isConfirmingDelete = confirmDeleteId === conv.id;
          const isDeleting = deletingId === conv.id;

          return (
            <div
              key={conv.id}
              onClick={() => !isRenaming && onSelectConversation(conv.id)}
              style={{
                padding: isOpen ? '9px 10px' : '9px 6px',
                borderRadius: 'var(--radius-md)',
                background: isActive ? 'var(--accent-muted)' : 'transparent',
                border: '1px solid',
                borderColor: isActive ? 'var(--accent-primary)' : 'transparent',
                cursor: 'pointer',
                marginBottom: '3px',
                transition: 'all var(--transition-fast)',
                opacity: isDeleting ? 0.5 : 1,
              }}
              onMouseEnter={e => {
                if (!isActive) {
                  e.currentTarget.style.background = 'var(--bg-tertiary)';
                  e.currentTarget.style.borderColor = 'var(--border-subtle)';
                }
              }}
              onMouseLeave={e => {
                if (!isActive) {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.borderColor = 'transparent';
                }
              }}
              role="button"
              aria-selected={isActive}
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && onSelectConversation(conv.id)}
            >
              {!isOpen ? (
                /* Collapsed — just icon */
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <MessageSquare
                    size={16}
                    color={isActive ? 'var(--accent-primary)' : 'var(--text-muted)'}
                  />
                </div>
              ) : isRenaming ? (
                /* Rename inline editor */
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                  onClick={e => e.stopPropagation()}
                >
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={e => setRenameValue(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') commitRename(conv.id);
                      if (e.key === 'Escape') cancelRename();
                    }}
                    style={{
                      flex: 1, padding: '4px 8px', fontSize: '12px',
                      background: 'var(--bg-input)',
                      border: '1px solid var(--accent-primary)',
                      borderRadius: 'var(--radius-sm)',
                      color: 'var(--text-primary)',
                    }}
                  />
                  <button
                    onClick={e => commitRename(conv.id, e)}
                    style={{ color: 'var(--color-success)', padding: '2px' }}
                    aria-label="Save rename"
                  >
                    <Check size={13} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); cancelRename(); }}
                    style={{ color: 'var(--text-muted)', padding: '2px' }}
                    aria-label="Cancel rename"
                  >
                    <X size={13} />
                  </button>
                </div>
              ) : isConfirmingDelete ? (
                /* Delete confirmation */
                <div
                  style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}
                  onClick={e => e.stopPropagation()}
                >
                  <p style={{ fontSize: '11px', color: 'var(--color-danger)', lineHeight: 1.3 }}>
                    Delete this conversation?
                  </p>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button
                      onClick={e => confirmDelete(conv.id, e)}
                      style={{
                        flex: 1, padding: '4px', fontSize: '11px',
                        borderRadius: 'var(--radius-sm)',
                        background: 'rgba(239,68,68,0.15)',
                        border: '1px solid rgba(239,68,68,0.4)',
                        color: '#ef4444', cursor: 'pointer',
                      }}
                      aria-label="Confirm delete"
                    >
                      {isDeleting ? <Loader2 size={11} className="animate-spin-slow" /> : 'Delete'}
                    </button>
                    <button
                      onClick={cancelDelete}
                      style={{
                        flex: 1, padding: '4px', fontSize: '11px',
                        borderRadius: 'var(--radius-sm)',
                        background: 'var(--bg-tertiary)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-secondary)', cursor: 'pointer',
                      }}
                      aria-label="Cancel delete"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                /* Normal conversation row */
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                  <MessageSquare
                    size={14}
                    color={isActive ? 'var(--accent-primary)' : 'var(--text-muted)'}
                    style={{ marginTop: '2px', flexShrink: 0 }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{
                      fontSize: '12px', fontWeight: isActive ? 600 : 400,
                      color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      lineHeight: 1.3,
                    }}>
                      {conv.title}
                    </p>
                    <div style={{
                      display: 'flex', gap: '8px', marginTop: '3px',
                      fontSize: '10px', color: 'var(--text-muted)',
                      fontFamily: 'var(--font-mono)',
                    }}>
                      <span>{formatDate(conv.updated_at)}</span>
                      {conv.message_count > 0 && (
                        <span>{conv.message_count} msg</span>
                      )}
                      {conv.document_count > 0 && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                          <FileText size={9} /> {conv.document_count}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Action icons — only visible on hover/active */}
                  <div
                    className="conv-actions"
                    style={{ display: 'flex', gap: '3px', flexShrink: 0 }}
                    onClick={e => e.stopPropagation()}
                  >
                    <button
                      onClick={e => startRename(conv, e)}
                      title="Rename"
                      style={{
                        width: '20px', height: '20px',
                        borderRadius: '4px', background: 'transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        cursor: 'pointer', color: 'var(--text-muted)',
                        opacity: isActive ? 1 : 0.4,
                        transition: 'opacity var(--transition-fast)',
                      }}
                      aria-label="Rename conversation"
                    >
                      <PencilLine size={11} />
                    </button>
                    <button
                      onClick={e => askDelete(conv.id, e)}
                      title="Delete"
                      style={{
                        width: '20px', height: '20px',
                        borderRadius: '4px', background: 'transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        cursor: 'pointer', color: 'var(--color-danger)',
                        opacity: isActive ? 1 : 0.3,
                        transition: 'opacity var(--transition-fast)',
                      }}
                      aria-label="Delete conversation"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
