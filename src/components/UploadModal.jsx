import React, { useState, useRef } from 'react';
import {
  UploadCloud, X, FileText, CheckCircle2,
  AlertCircle, Loader2,
} from 'lucide-react';
import { documents as docsApi } from '../utils/api';

const MAX_SIZE_MB = 50;

export default function UploadModal({ isOpen, onClose, conversationId, onUploadComplete }) {
  const [files, setFiles]       = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading]   = useState(false);
  const [results, setResults]       = useState(null);
  const inputRef = useRef(null);

  if (!isOpen) return null;

  const addFiles = (incoming) => {
    const pdfs   = Array.from(incoming).filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
    const tooBig = Array.from(incoming).filter(f => f.size > MAX_SIZE_MB * 1024 * 1024);
    setFiles(prev => {
      const existing = new Set(prev.map(f => f.name));
      return [...prev, ...pdfs.filter(f => !existing.has(f.name))];
    });
    if (tooBig.length > 0) {
      setResults(prev => (prev || []).concat(
        tooBig.map(f => ({ filename: f.name, status: 'failed', error: `Exceeds ${MAX_SIZE_MB} MB limit` }))
      ));
    }
  };

  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation();
    setDragActive(false);
    addFiles(e.dataTransfer.files);
  };

  const removeFile = (name) => setFiles(f => f.filter(x => x.name !== name));

  const handleUpload = async () => {
    if (!files.length || !conversationId) return;
    setUploading(true);
    setResults(null);
    try {
      const res = await docsApi.upload(conversationId, files);
      setResults(res.results);
      if (res.accepted > 0) onUploadComplete?.();
    } catch (err) {
      setResults([{ filename: 'Upload', status: 'failed', error: err.message }]);
    } finally {
      setUploading(false);
    }
  };

  const handleClose = () => {
    if (uploading) return;
    setFiles([]); setResults(null); onClose();
  };

  const allDone = results && !uploading;

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 200, padding: '20px',
      }}
      onClick={e => { if (e.target === e.currentTarget && !uploading) handleClose(); }}
      role="dialog" aria-modal="true" aria-label="Upload documents"
    >
      <div style={{
        width: '100%', maxWidth: '480px',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-medium)',
        borderRadius: 'var(--radius-xl)',
        boxShadow: 'var(--shadow-lg)',
        display: 'flex', flexDirection: 'column',
        maxHeight: '90vh', overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '30px', height: '30px', borderRadius: '8px',
              background: 'var(--accent-muted)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <UploadCloud size={16} color="var(--accent-primary)" />
            </div>
            <div>
              <h3 style={{ fontSize: '15px', color: 'var(--text-primary)', fontWeight: 600 }}>
                Upload PDFs
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                PDF only · max {MAX_SIZE_MB} MB each · multiple files supported
              </p>
            </div>
          </div>
          <button onClick={handleClose} disabled={uploading}
            style={{ color: 'var(--text-muted)', padding: '4px', borderRadius: 'var(--radius-sm)', background: 'none', border: 'none', cursor: 'pointer' }}
            aria-label="Close">
            <X size={17} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
          {!allDone ? (
            <>
              {/* Drop zone */}
              <div
                onDrop={handleDrop}
                onDragOver={e => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onClick={() => !uploading && inputRef.current?.click()}
                style={{
                  border: `2px dashed ${dragActive ? 'var(--accent-primary)' : 'var(--border-medium)'}`,
                  borderRadius: 'var(--radius-lg)',
                  padding: '32px 20px', textAlign: 'center',
                  background: dragActive ? 'var(--accent-muted)' : 'var(--bg-tertiary)',
                  cursor: uploading ? 'not-allowed' : 'pointer',
                  transition: 'all var(--transition-fast)',
                }}
              >
                <input ref={inputRef} type="file" accept=".pdf,application/pdf" multiple
                  style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} disabled={uploading} />
                <UploadCloud size={30} color={dragActive ? 'var(--accent-primary)' : 'var(--text-muted)'}
                  style={{ margin: '0 auto 12px' }} />
                <p style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '4px' }}>
                  {dragActive ? 'Drop PDFs here' : 'Click or drag & drop PDFs'}
                </p>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Multiple files supported</p>
              </div>

              {/* Selected files */}
              {files.length > 0 && (
                <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {files.map(f => (
                    <div key={f.name} style={{
                      display: 'flex', alignItems: 'center', gap: '10px',
                      padding: '8px 12px',
                      background: 'var(--bg-tertiary)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-md)',
                    }}>
                      <FileText size={13} color="var(--accent-primary)" />
                      <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {f.name}
                      </span>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                        {(f.size / (1024 * 1024)).toFixed(1)} MB
                      </span>
                      {!uploading && (
                        <button onClick={() => removeFile(f.name)}
                          style={{ color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '2px' }}
                          aria-label={`Remove ${f.name}`}>
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            /* Results */
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {results.map((r, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: '10px',
                  padding: '10px 14px',
                  background: r.status === 'failed' ? 'rgba(239,68,68,0.06)' : 'rgba(16,185,129,0.06)',
                  border: `1px solid ${r.status === 'failed' ? 'rgba(239,68,68,0.25)' : 'rgba(16,185,129,0.25)'}`,
                  borderRadius: 'var(--radius-md)',
                }}>
                  {r.status === 'failed'
                    ? <AlertCircle size={15} color="var(--color-danger)" style={{ flexShrink: 0, marginTop: '1px' }} />
                    : <CheckCircle2 size={15} color="var(--color-success)" style={{ flexShrink: 0, marginTop: '1px' }} />
                  }
                  <div>
                    <p style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>{r.filename}</p>
                    {r.error && <p style={{ fontSize: '11px', color: 'var(--color-danger)', marginTop: '2px' }}>{r.error}</p>}
                    {r.status !== 'failed' && (
                      <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                        Processing — check the document list for status updates.
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '14px 20px', borderTop: '1px solid var(--border-subtle)',
          display: 'flex', justifyContent: 'flex-end', gap: '10px', flexShrink: 0,
        }}>
          {allDone ? (
            <button onClick={handleClose} className="btn-primary">Done</button>
          ) : (
            <>
              <button onClick={handleClose} disabled={uploading} className="btn-ghost">Cancel</button>
              <button
                onClick={handleUpload}
                disabled={!files.length || uploading}
                className="btn-primary"
                style={{ display: 'flex', alignItems: 'center', gap: '7px' }}
              >
                {uploading
                  ? <><Loader2 size={14} className="animate-spin-slow" /><span>Uploading…</span></>
                  : <><UploadCloud size={14} /><span>Upload{files.length > 0 ? ` ${files.length} file${files.length > 1 ? 's' : ''}` : ''}</span></>
                }
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
