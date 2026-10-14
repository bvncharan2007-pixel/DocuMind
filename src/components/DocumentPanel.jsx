import React, { useState, useEffect, useRef } from 'react';
import {
  FileText, UploadCloud, Trash2, RefreshCw,
  CheckCircle2, AlertCircle, Loader2, Clock, X,
} from 'lucide-react';
import { documents as docsApi } from '../utils/api';

const STATUS_POLL_MS = 3000; // poll every 3 s while docs are processing

/**
 * Document management panel embedded in the workspace.
 * Shows all documents for the active conversation, allows deletion,
 * and auto-polls to update processing status.
 */
export default function DocumentPanel({
  conversationId,
  documents,
  onRefresh,
  onOpenUpload,
}) {
  const [deletingId, setDeletingId] = useState(null);
  const [confirmId, setConfirmId]   = useState(null);
  const [error, setError]           = useState('');
  const pollTimer = useRef(null);

  // Auto-poll when any document is still processing/pending
  useEffect(() => {
    const needsPoll = documents.some(d => d.status === 'pending' || d.status === 'processing');
    if (needsPoll) {
      pollTimer.current = setTimeout(onRefresh, STATUS_POLL_MS);
    }
    return () => clearTimeout(pollTimer.current);
  }, [documents, onRefresh]);

  const handleDelete = async (docId) => {
    setDeletingId(docId);
    setError('');
    try {
      await docsApi.delete(conversationId, docId);
      setConfirmId(null);
      onRefresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingId(null);
    }
  };

  if (!conversationId) return null;

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: '0',
      background: 'var(--bg-secondary)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
          <FileText size={14} color="var(--accent-primary)" />
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Documents
          </span>
          <span style={{
            fontSize: '10px', fontFamily: 'var(--font-mono)',
            padding: '1px 6px', borderRadius: 'var(--radius-full)',
            background: 'var(--accent-muted)', color: 'var(--accent-primary)',
          }}>
            {documents.length}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button
            onClick={onRefresh}
            title="Refresh"
            style={{
              padding: '3px', background: 'none', border: 'none',
              cursor: 'pointer', color: 'var(--text-muted)',
              borderRadius: 'var(--radius-sm)',
            }}
            aria-label="Refresh document list"
          >
            <RefreshCw size={12} />
          </button>
          <button
            onClick={onOpenUpload}
            style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '4px 9px',
              background: 'var(--accent-muted)',
              border: '1px solid var(--accent-primary)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--accent-primary)',
              fontSize: '11px', fontWeight: 500,
              cursor: 'pointer',
            }}
            aria-label="Upload more PDFs"
          >
            <UploadCloud size={11} />
            <span>Add</span>
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: '8px 14px',
          background: 'rgba(239,68,68,0.07)',
          borderBottom: '1px solid rgba(239,68,68,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: '8px',
        }}>
          <span style={{ fontSize: '11px', color: 'var(--color-danger)' }}>{error}</span>
          <button onClick={() => setError('')} style={{ color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={12} />
          </button>
        </div>
      )}

      {/* Document list */}
      <div style={{ maxHeight: '220px', overflowY: 'auto' }}>
        {documents.length === 0 ? (
          <div style={{
            padding: '20px 14px', textAlign: 'center',
            color: 'var(--text-muted)', fontSize: '12px',
          }}>
            No documents yet. Upload PDFs to get started.
          </div>
        ) : (
          documents.map(doc => (
            <DocRow
              key={doc.id}
              doc={doc}
              isDeleting={deletingId === doc.id}
              isConfirming={confirmId === doc.id}
              onAskDelete={() => setConfirmId(doc.id)}
              onConfirmDelete={() => handleDelete(doc.id)}
              onCancelDelete={() => setConfirmId(null)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function DocRow({ doc, isDeleting, isConfirming, onAskDelete, onConfirmDelete, onCancelDelete }) {
  const statusColor = {
    completed:  'var(--color-success)',
    processing: 'var(--color-info)',
    pending:    'var(--color-warning)',
    failed:     'var(--color-danger)',
  }[doc.status] || 'var(--text-muted)';

  const StatusIcon = {
    completed:  CheckCircle2,
    processing: Loader2,
    pending:    Clock,
    failed:     AlertCircle,
  }[doc.status] || Clock;

  return (
    <div style={{
      padding: '9px 14px',
      borderBottom: '1px solid var(--border-subtle)',
      opacity: isDeleting ? 0.5 : 1,
      transition: 'opacity var(--transition-fast)',
    }}>
      {isConfirming ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '11px', color: 'var(--color-danger)', flex: 1 }}>
            Delete "{doc.original_filename}"?
          </span>
          <button
            onClick={onConfirmDelete}
            disabled={isDeleting}
            style={{
              padding: '3px 9px', fontSize: '11px',
              background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.35)',
              borderRadius: 'var(--radius-sm)', color: '#ef4444', cursor: 'pointer',
            }}
          >
            {isDeleting ? <Loader2 size={11} className="animate-spin-slow" /> : 'Delete'}
          </button>
          <button
            onClick={onCancelDelete}
            style={{
              padding: '3px 9px', fontSize: '11px',
              background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FileText size={13} color="var(--accent-primary)" style={{ flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{
              fontSize: '12px', color: 'var(--text-primary)', fontWeight: 500,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {doc.original_filename}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '2px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                <StatusIcon
                  size={10}
                  color={statusColor}
                  className={doc.status === 'processing' ? 'animate-spin-slow' : ''}
                />
                <span style={{ fontSize: '10px', color: statusColor, fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                  {doc.status.toUpperCase()}
                </span>
              </div>
              {doc.page_count && (
                <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {doc.page_count}p
                </span>
              )}
              {doc.error_message && (
                <span style={{ fontSize: '10px', color: 'var(--color-danger)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '140px' }}>
                  {doc.error_message}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onAskDelete}
            title="Remove document"
            style={{
              padding: '3px', background: 'none', border: 'none',
              cursor: 'pointer', color: 'var(--text-muted)',
              borderRadius: 'var(--radius-sm)',
              flexShrink: 0,
            }}
            aria-label={`Delete ${doc.original_filename}`}
          >
            <Trash2 size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
