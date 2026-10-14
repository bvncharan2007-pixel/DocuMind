import React from 'react';
import {
  FileText, UploadCloud, Settings, Sparkles,
  ShieldCheck, LogOut, LayoutDashboard, BookOpen,
} from 'lucide-react';
import ThemeToggle from './ThemeToggle';

export default function Header({
  currentUser,
  currentView,
  onSwitchView,
  onLogout,
  onOpenUpload,
  onOpenSettings,
  theme,
  onToggleTheme,
  activeConversation,
}) {
  return (
    <header
      className="glass-nav"
      style={{
        height: 'var(--header-height)',
        padding: '0 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'relative',
        zIndex: 40,
        flexShrink: 0,
      }}
    >
      {/* ── Brand ── */}
      <button
        onClick={() => onSwitchView('workspace')}
        style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          background: 'none', cursor: 'pointer', border: 'none',
        }}
        aria-label="DocuMind home"
      >
        <div style={{
          width: '34px', height: '34px', borderRadius: '10px',
          background: 'var(--gradient-brand)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: 'var(--shadow-glow)', flexShrink: 0,
        }}>
          <Sparkles size={18} color="#ffffff" />
        </div>
        <div style={{ textAlign: 'left' }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: '17px',
            fontWeight: 700, letterSpacing: '-0.02em',
            color: 'var(--text-primary)',
          }}>
            Docu<span className="text-gradient">Mind</span>
          </span>
          {activeConversation && (
            <p style={{
              fontSize: '11px', color: 'var(--text-muted)',
              lineHeight: 1, marginTop: '1px',
              maxWidth: '200px', overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {activeConversation.title}
            </p>
          )}
        </div>
      </button>

      {/* ── Right controls ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>

        {/* Upload (workspace only) */}
        {currentView === 'workspace' && onOpenUpload && (
          <button
            onClick={onOpenUpload}
            className="btn-ghost"
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px' }}
            aria-label="Upload documents"
          >
            <UploadCloud size={14} color="var(--accent-primary)" />
            <span style={{ fontSize: '12px' }}>Upload</span>
          </button>
        )}

        {/* Admin ↔ Workspace switcher */}
        {currentUser?.role === 'admin' && (
          <button
            onClick={() => onSwitchView(currentView === 'admin' ? 'workspace' : 'admin')}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '6px 12px',
              borderRadius: 'var(--radius-md)',
              background: currentView === 'admin' ? 'var(--accent-muted)' : 'transparent',
              border: '1px solid var(--border-medium)',
              color: 'var(--text-secondary)',
              fontSize: '12px', fontWeight: 500,
              cursor: 'pointer',
              transition: 'all var(--transition-fast)',
            }}
            aria-label={currentView === 'admin' ? 'Open workspace' : 'Open admin console'}
          >
            {currentView === 'admin'
              ? <><BookOpen size={14} /><span>Workspace</span></>
              : <><LayoutDashboard size={14} /><span>Admin</span></>
            }
          </button>
        )}

        {/* Settings */}
        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            style={{
              width: '32px', height: '32px', borderRadius: 'var(--radius-md)',
              background: 'transparent', border: '1px solid var(--border-subtle)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', color: 'var(--text-muted)',
            }}
            aria-label="Settings"
          >
            <Settings size={15} />
          </button>
        )}

        {/* Theme toggle */}
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />

        <div style={{ width: '1px', height: '20px', background: 'var(--border-subtle)' }} />

        {/* User chip */}
        {currentUser && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-full)',
            padding: '3px 10px 3px 4px',
          }}>
            <div style={{
              width: '24px', height: '24px', borderRadius: '50%',
              background: 'var(--gradient-brand)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '11px', fontWeight: 700, color: '#ffffff',
              flexShrink: 0,
            }}>
              {currentUser.username.slice(0, 1).toUpperCase()}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1 }}>
                {currentUser.username}
              </span>
              <span style={{
                fontSize: '9px', color: 'var(--accent-primary)',
                fontFamily: 'var(--font-mono)', textTransform: 'uppercase',
              }}>
                {currentUser.role}
              </span>
            </div>
          </div>
        )}

        {/* Logout */}
        <button
          onClick={onLogout}
          title="Sign out"
          style={{
            width: '32px', height: '32px', borderRadius: 'var(--radius-md)',
            background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', color: 'var(--color-danger)',
          }}
          aria-label="Sign out"
        >
          <LogOut size={14} />
        </button>
      </div>
    </header>
  );
}
