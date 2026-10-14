import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles, Send, Bot, User, Copy, Check,
  AlertCircle, FileText, Loader2, ChevronDown,
} from 'lucide-react';

/**
 * Chat panel — calls the real /api/conversations/{id}/ask endpoint.
 * All Q&A is backend-powered; no local mock engine.
 */
export default function AiCopilot({
  conversationId,
  messages,           // MessageResponse[] from backend
  documents,          // DocumentResponse[] — completed docs for this conv
  onSendQuestion,     // (question: string) => Promise<void>
  isSending,
}) {
  const [input, setInput] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const messagesEndRef = useRef(null);
  const scrollAreaRef  = useRef(null);

  // Auto-scroll when new messages arrive (unless user scrolled up)
  useEffect(() => {
    if (autoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isSending, autoScroll]);

  const handleScroll = () => {
    const el = scrollAreaRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setAutoScroll(nearBottom);
  };

  const handleSend = () => {
    const q = input.trim();
    if (!q || isSending) return;
    setInput('');
    setAutoScroll(true);
    onSendQuestion(q);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    setAutoScroll(true);
  };

  const completedDocs = (documents || []).filter(d => d.status === 'completed');
  const hasNoDocs = completedDocs.length === 0;

  return (
    <div style={{
      width: '400px', minWidth: '340px', flexShrink: 0,
      display: 'flex', flexDirection: 'column',
      background: 'var(--bg-secondary)',
      borderLeft: '1px solid var(--border-subtle)',
      height: '100%', overflow: 'hidden',
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            width: '26px', height: '26px', borderRadius: '7px',
            background: 'var(--gradient-brand)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Bot size={14} color="#ffffff" />
          </div>
          <div>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
              AI Assistant
            </span>
            <p style={{ fontSize: '10px', color: 'var(--text-muted)', lineHeight: 1 }}>
              {completedDocs.length > 0
                ? `${completedDocs.length} document${completedDocs.length > 1 ? 's' : ''} ready`
                : 'No documents indexed'
              }
            </p>
          </div>
        </div>

        {/* Scroll-to-bottom when not at bottom */}
        {!autoScroll && (
          <button
            onClick={scrollToBottom}
            title="Scroll to bottom"
            style={{
              width: '26px', height: '26px', borderRadius: '50%',
              background: 'var(--accent-muted)', border: '1px solid var(--accent-primary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', color: 'var(--accent-primary)',
            }}
            aria-label="Scroll to bottom"
          >
            <ChevronDown size={13} />
          </button>
        )}
      </div>

      {/* ── Messages area ── */}
      <div
        ref={scrollAreaRef}
        onScroll={handleScroll}
        style={{
          flex: 1, overflowY: 'auto', padding: '14px',
          display: 'flex', flexDirection: 'column', gap: '14px',
        }}
      >
        {/* Empty state */}
        {messages.length === 0 && !isSending && (
          <EmptyState hasNoDocs={hasNoDocs} docs={completedDocs} onSuggest={(q) => {
            setInput(q);
          }} />
        )}

        {/* Message list */}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            copiedId={copiedId}
            onCopy={handleCopy}
          />
        ))}

        {/* Sending indicator */}
        {isSending && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '10px 14px',
            background: 'var(--bubble-ai)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            alignSelf: 'flex-start',
            maxWidth: '90%',
          }}>
            <Loader2 size={14} className="animate-spin-slow" color="var(--accent-primary)" />
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Searching documents and generating answer…
            </span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── No-documents warning ── */}
      {hasNoDocs && (
        <div style={{
          padding: '8px 14px',
          background: 'rgba(245,158,11,0.06)',
          borderTop: '1px solid rgba(245,158,11,0.2)',
          display: 'flex', alignItems: 'center', gap: '8px',
          flexShrink: 0,
        }}>
          <AlertCircle size={13} color="var(--color-warning)" />
          <span style={{ fontSize: '11px', color: 'var(--color-warning)' }}>
            Upload and process PDFs before asking questions.
          </span>
        </div>
      )}

      {/* ── Input bar ── */}
      <div style={{
        padding: '12px 14px',
        borderTop: '1px solid var(--border-subtle)',
        background: 'var(--bg-secondary)',
        flexShrink: 0,
      }}>
        <div style={{
          display: 'flex', alignItems: 'flex-end', gap: '8px',
          background: 'var(--bg-input)',
          border: '1px solid var(--border-medium)',
          borderRadius: 'var(--radius-lg)',
          padding: '8px 8px 8px 14px',
          transition: 'border-color var(--transition-fast)',
        }}
          onFocusCapture={e => e.currentTarget.style.borderColor = 'var(--accent-primary)'}
          onBlurCapture={e => e.currentTarget.style.borderColor = 'var(--border-medium)'}
        >
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={hasNoDocs
              ? 'Upload documents first…'
              : 'Ask a question about your documents…'
            }
            disabled={isSending}
            rows={1}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              color: 'var(--text-primary)',
              fontSize: '13px',
              lineHeight: 1.5,
              resize: 'none',
              maxHeight: '120px',
              overflowY: 'auto',
            }}
            aria-label="Question input"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isSending}
            title="Send (Enter)"
            style={{
              width: '32px', height: '32px',
              borderRadius: 'var(--radius-md)',
              background: input.trim() && !isSending
                ? 'var(--gradient-brand)'
                : 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: input.trim() && !isSending ? 'pointer' : 'not-allowed',
              transition: 'all var(--transition-fast)',
              flexShrink: 0,
            }}
            aria-label="Send question"
          >
            <Send size={14} color={input.trim() && !isSending ? '#ffffff' : 'var(--text-muted)'} />
          </button>
        </div>
        <p style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '5px', paddingLeft: '2px' }}>
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}

/* ── Message bubble ── */
function MessageBubble({ msg, copiedId, onCopy }) {
  const isUser = msg.role === 'user';
  const hasCitations = !isUser && msg.citations && msg.citations.length > 0;
  const isError = !isUser && msg.content?.startsWith('[Error]');

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignSelf: isUser ? 'flex-end' : 'flex-start',
      maxWidth: '92%',
      gap: '6px',
      animationName: 'fadeIn',
      animationDuration: '0.2s',
      animationFillMode: 'both',
    }}>
      {/* Role label */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '5px',
        fontSize: '10px', color: 'var(--text-muted)',
        alignSelf: isUser ? 'flex-end' : 'flex-start',
      }}>
        {isUser
          ? <><User size={11} /><span>You</span></>
          : <><Bot size={11} color="var(--accent-primary)" /><span>DocuMind</span></>
        }
        {msg.created_at && (
          <span style={{ opacity: 0.6 }}>
            · {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>

      {/* Bubble */}
      <div style={{
        padding: '10px 13px',
        borderRadius: 'var(--radius-md)',
        background: isUser
          ? 'var(--bubble-user)'
          : isError
            ? 'rgba(239,68,68,0.07)'
            : 'var(--bubble-ai)',
        border: '1px solid',
        borderColor: isUser
          ? 'transparent'
          : isError
            ? 'rgba(239,68,68,0.25)'
            : 'var(--bubble-ai-border)',
        color: isUser ? 'var(--bubble-user-text)' : 'var(--bubble-ai-text)',
        fontSize: '13px',
        lineHeight: 1.65,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}>
        {isError && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
            <AlertCircle size={13} color="var(--color-danger)" />
            <span style={{ fontSize: '11px', color: 'var(--color-danger)', fontWeight: 600 }}>
              Generation error
            </span>
          </div>
        )}
        {msg.content}
      </div>

      {/* Copy + citations */}
      {!isUser && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingLeft: '2px' }}>
          <button
            onClick={() => onCopy(msg.content, msg.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '11px', color: 'var(--text-muted)',
              background: 'none', border: 'none', cursor: 'pointer', width: 'fit-content',
            }}
            aria-label="Copy answer"
          >
            {copiedId === msg.id
              ? <><Check size={11} color="var(--color-success)" /><span style={{ color: 'var(--color-success)' }}>Copied</span></>
              : <><Copy size={11} /><span>Copy</span></>
            }
          </button>

          {hasCitations && <CitationList citations={msg.citations} />}
        </div>
      )}
    </div>
  );
}

/* ── Citations ── */
function CitationList({ citations }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? citations : citations.slice(0, 2);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <p style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
        Sources
      </p>
      {visible.map((c, i) => (
        <div
          key={i}
          style={{
            padding: '7px 10px',
            background: 'var(--accent-muted)',
            border: '1px solid var(--accent-glow)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: c.excerpt ? '4px' : 0 }}>
            <FileText size={11} color="var(--accent-primary)" />
            <span style={{ color: 'var(--text-primary)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {c.filename}
            </span>
            <span style={{
              flexShrink: 0,
              padding: '1px 6px', borderRadius: 'var(--radius-full)',
              background: 'var(--accent-muted)',
              border: '1px solid var(--accent-glow)',
              color: 'var(--accent-light)',
              fontFamily: 'var(--font-mono)', fontSize: '10px',
            }}>
              p.{c.page_range}
            </span>
          </div>
          {c.excerpt && (
            <p style={{
              color: 'var(--text-secondary)', fontSize: '11px',
              lineHeight: 1.4, fontStyle: 'italic',
              display: '-webkit-box', WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical', overflow: 'hidden',
            }}>
              "{c.excerpt}"
            </p>
          )}
        </div>
      ))}
      {citations.length > 2 && (
        <button
          onClick={() => setExpanded(e => !e)}
          style={{ fontSize: '11px', color: 'var(--accent-primary)', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
        >
          {expanded ? 'Show less' : `+${citations.length - 2} more source${citations.length - 2 > 1 ? 's' : ''}`}
        </button>
      )}
    </div>
  );
}

/* ── Empty state ── */
function EmptyState({ hasNoDocs, docs, onSuggest }) {
  const suggestions = [
    'Summarize the key findings of these documents.',
    'What are the main risks or limitations mentioned?',
    'Extract the most important numbers and metrics.',
    'What are the recommendations in these documents?',
  ];

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '24px', gap: '16px', textAlign: 'center',
    }}>
      <div style={{
        width: '48px', height: '48px', borderRadius: '14px',
        background: 'var(--gradient-brand)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: 'var(--shadow-glow)',
      }}>
        <Sparkles size={22} color="#ffffff" />
      </div>

      <div>
        <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
          {hasNoDocs ? 'No documents ready' : 'Ready to answer questions'}
        </h3>
        <p style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
          {hasNoDocs
            ? 'Upload and process PDFs using the panel on the left, then ask questions here.'
            : `Ask anything about your ${docs.length} document${docs.length > 1 ? 's' : ''}. Answers are grounded in the actual content.`
          }
        </p>
      </div>

      {!hasNoDocs && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
          <p style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
            Try asking:
          </p>
          {suggestions.map((q, i) => (
            <button
              key={i}
              onClick={() => onSuggest(q)}
              style={{
                textAlign: 'left', padding: '8px 12px',
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-secondary)',
                fontSize: '12px', lineHeight: 1.4,
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = 'var(--accent-muted)';
                e.currentTarget.style.borderColor = 'var(--accent-primary)';
                e.currentTarget.style.color = 'var(--text-primary)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'var(--bg-tertiary)';
                e.currentTarget.style.borderColor = 'var(--border-subtle)';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
