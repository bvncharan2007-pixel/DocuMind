import React, { useState } from 'react';
import { Clock, ShieldAlert, LogOut, RefreshCw, Sparkles } from 'lucide-react';

const cardBase = {
  width: '100%',
  maxWidth: '460px',
  background: 'var(--bg-secondary)',
  border: '1px solid var(--border-medium)',
  borderRadius: 'var(--radius-xl)',
  padding: '36px',
  textAlign: 'center',
  boxShadow: 'var(--shadow-lg)',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: '20px',
};

const screenBase = {
  width: '100vw',
  height: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bg-primary)',
  padding: '20px',
};

export function PendingScreen({ user, onCheckStatus, onLogout }) {
  const [checking, setChecking] = useState(false);

  const handleRefresh = async () => {
    setChecking(true);
    try { await onCheckStatus(); } finally {
      setTimeout(() => setChecking(false), 600);
    }
  };

  return (
    <div style={screenBase}>
      <div style={cardBase}>
        <div style={{
          width: '52px', height: '52px', borderRadius: '14px',
          background: 'rgba(245,158,11,0.12)',
          border: '1px solid rgba(245,158,11,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Clock size={26} color="var(--color-warning)" />
        </div>

        <div>
          <span style={{
            fontSize: '10px', fontFamily: 'var(--font-mono)', fontWeight: 600,
            textTransform: 'uppercase', color: 'var(--color-warning)',
            background: 'rgba(245,158,11,0.1)', padding: '3px 10px',
            borderRadius: 'var(--radius-full)',
          }}>
            Pending Approval
          </span>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '10px' }}>
            Account Under Review
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6, marginTop: '8px' }}>
            Welcome, <strong style={{ color: 'var(--text-primary)' }}>{user.username}</strong>.
            Your registration is awaiting administrator approval.
          </p>
        </div>

        <div style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 16px', textAlign: 'left', width: '100%',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '6px' }}>
            <Sparkles size={13} color="var(--accent-primary)" />
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Next steps
            </span>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            An administrator will review your request. You'll gain full access once approved.
            Click "Check Status" to refresh.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px', width: '100%' }}>
          <button
            onClick={handleRefresh}
            disabled={checking}
            style={{
              flex: 1, padding: '10px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--accent-muted)',
              border: '1px solid var(--accent-primary)',
              color: 'var(--accent-primary)',
              fontSize: '13px', fontWeight: 600,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
              cursor: checking ? 'not-allowed' : 'pointer',
            }}
          >
            <RefreshCw size={14} className={checking ? 'animate-spin-slow' : ''} />
            {checking ? 'Checking…' : 'Check Status'}
          </button>
          <button
            onClick={onLogout}
            className="btn-ghost"
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <LogOut size={14} />
            Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}

export function AccessDeniedScreen({ user, onLogout }) {
  const isDeactivated = user.status === 'deactivated';
  return (
    <div style={screenBase}>
      <div style={{ ...cardBase, border: '1px solid rgba(239,68,68,0.3)' }}>
        <div style={{
          width: '52px', height: '52px', borderRadius: '14px',
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <ShieldAlert size={26} color="var(--color-danger)" />
        </div>

        <div>
          <span style={{
            fontSize: '10px', fontFamily: 'var(--font-mono)', fontWeight: 600,
            textTransform: 'uppercase', color: 'var(--color-danger)',
            background: 'rgba(239,68,68,0.1)', padding: '3px 10px',
            borderRadius: 'var(--radius-full)',
          }}>
            {user.status.toUpperCase()}
          </span>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '10px' }}>
            Access Denied
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6, marginTop: '8px' }}>
            {isDeactivated
              ? 'Your account has been deactivated. Contact an administrator for assistance.'
              : 'Your account registration was not approved. Contact an administrator.'}
          </p>
        </div>

        <button
          onClick={onLogout}
          className="btn-primary"
          style={{ width: '100%', justifyContent: 'center', display: 'flex', gap: '8px' }}
        >
          <LogOut size={15} />
          Return to Sign In
        </button>
      </div>
    </div>
  );
}
