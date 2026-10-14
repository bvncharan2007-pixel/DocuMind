import React, { useState, useEffect } from 'react';
import {
  Users, ShieldCheck, UserCheck, UserX, UserMinus,
  UserPlus, Activity, Search, RefreshCw, Check, X, BookOpen,
  Clock, AlertTriangle,
} from 'lucide-react';
import ThemeToggle from './ThemeToggle';
import { admin as adminApi } from '../utils/api';

export default function AdminDashboard({ currentUser, csrfToken, onSwitchToWorkspace, theme, onToggleTheme }) {
  const [users, setUsers] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [activeTab, setActiveTab] = useState('users'); // 'users' | 'audit'
  const [filterStatus, setFilterStatus] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [actionError, setActionError] = useState('');

  // Admin New User modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [newStatus, setNewStatus] = useState('approved');
  const [createLoading, setCreateLoading] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    setActionError('');
    try {
      const data = await adminApi.users();
      setUsers(data);
    } catch (err) {
      setActionError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchAuditLogs = async () => {
    try {
      const data = await adminApi.auditLogs(100);
      setAuditLogs(data);
    } catch (err) {
      console.error('Audit log fetch error:', err.message);
    }
  };

  useEffect(() => {
    fetchUsers();
    fetchAuditLogs();
  }, []);

  const handleUpdateStatus = async (userId, targetStatus) => {
    setActionError('');
    try {
      const data = await adminApi.updateStatus(userId, targetStatus);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: data.status } : u));
      fetchAuditLogs();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const handleUpdateRole = async (userId, targetRole) => {
    setActionError('');
    try {
      const data = await adminApi.updateRole(userId, targetRole);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, role: data.role } : u));
      fetchAuditLogs();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setActionError('');
    setCreateLoading(true);
    try {
      await adminApi.createUser({
        username: newUsername.trim(),
        email: newEmail.trim(),
        password: newPassword,
        role: newRole,
        status: newStatus,
      });
      setShowCreateModal(false);
      setNewUsername(''); setNewEmail(''); setNewPassword('');
      fetchUsers(); fetchAuditLogs();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setCreateLoading(false);
    }
  };

  const filteredUsers = users.filter(u => {
    const matchesFilter = filterStatus === 'ALL' || u.status === filterStatus.toLowerCase();
    const matchesSearch = searchQuery === '' || 
      u.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const pendingCount     = users.filter(u => u.status === 'pending').length;
  const approvedCount    = users.filter(u => u.status === 'approved').length;
  const deactivatedCount = users.filter(u => u.status === 'deactivated').length;

  return (
    <div style={{
      width: '100%',
      height: 'calc(100vh - var(--header-height))',
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--bg-primary)',
      overflowY: 'auto',
      padding: '24px 28px',
    }}>
      {/* Top Banner */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h1 style={{ fontSize: '20px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            Admin Console
            <span style={{
              fontSize: '10px', fontFamily: 'var(--font-mono)',
              background: 'var(--accent-muted)', border: '1px solid var(--accent-primary)',
              color: 'var(--accent-primary)', padding: '2px 8px', borderRadius: 'var(--radius-full)',
            }}>RBAC v2</span>
          </h1>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '3px' }}>
            Account management and security audit logs
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          <button onClick={onSwitchToWorkspace} className="btn-ghost" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <BookOpen size={14} />
            <span>Workspace</span>
          </button>
          <button onClick={() => setShowCreateModal(true)} className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <UserPlus size={14} />
            <span>Provision User</span>
          </button>
        </div>
      </div>

      {/* Stats cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '20px' }}>
        {[
          { label: 'Total Accounts', value: users.length, color: 'var(--accent-primary)', icon: Users },
          { label: 'Approved', value: approvedCount, color: 'var(--color-success)', icon: UserCheck },
          { label: 'Pending Approval', value: pendingCount, color: 'var(--color-warning)', icon: Clock },
          { label: 'Deactivated', value: deactivatedCount, color: 'var(--color-danger)', icon: UserMinus },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            padding: '16px',
            display: 'flex', alignItems: 'center', gap: '12px',
          }}>
            <div style={{
              width: '36px', height: '36px', borderRadius: 'var(--radius-md)',
              background: `${color}18`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <Icon size={18} color={color} />
            </div>
            <div>
              <p style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{value}</p>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '3px' }}>{label}</p>
            </div>
          </div>
        ))}
      </div>

      {actionError && (
        <div style={{
          background: 'rgba(244, 63, 94, 0.12)',
          border: '1px solid rgba(244, 63, 94, 0.3)',
          borderRadius: 'var(--radius-md)',
          padding: '12px 16px',
          color: '#fecdd3',
          fontSize: '13px',
          marginBottom: '16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span>{actionError}</span>
          <button onClick={() => setActionError('')} style={{ color: '#fecdd3' }}>✕</button>
        </div>
      )}

      {/* Tabs */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: '1px solid var(--border-subtle)',
        paddingBottom: '12px',
        marginBottom: '20px'
      }}>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => setActiveTab('users')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              borderRadius: 'var(--radius-md)',
              background: activeTab === 'users' ? 'var(--accent-primary)' : 'rgba(255, 255, 255, 0.03)',
              color: activeTab === 'users' ? '#ffffff' : 'var(--text-muted)',
              fontSize: '13px',
              fontWeight: 600
            }}
          >
            <Users size={16} />
            <span>Account Management ({users.length})</span>
            {pendingCount > 0 && (
              <span style={{
                background: 'var(--accent-amber)',
                color: '#000000',
                fontSize: '10px',
                fontWeight: 700,
                padding: '1px 6px',
                borderRadius: 'var(--radius-full)'
              }}>
                {pendingCount} Pending
              </span>
            )}
          </button>

          <button
            onClick={() => { setActiveTab('audit'); fetchAuditLogs(); }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              borderRadius: 'var(--radius-md)',
              background: activeTab === 'audit' ? 'var(--accent-primary)' : 'rgba(255, 255, 255, 0.03)',
              color: activeTab === 'audit' ? '#ffffff' : 'var(--text-muted)',
              fontSize: '13px',
              fontWeight: 600
            }}
          >
            <Activity size={16} />
            <span>Security Audit Logs ({auditLogs.length})</span>
          </button>
        </div>

        {activeTab === 'users' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ display: 'flex', gap: '4px', background: 'rgba(0,0,0,0.3)', padding: '2px', borderRadius: 'var(--radius-sm)' }}>
              {['ALL', 'PENDING', 'APPROVED', 'DEACTIVATED'].map(st => (
                <button
                  key={st}
                  onClick={() => setFilterStatus(st)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '11px',
                    fontWeight: 500,
                    background: filterStatus === st ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
                    color: filterStatus === st ? '#ffffff' : 'var(--text-subtle)'
                  }}
                >
                  {st}
                </button>
              ))}
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              background: 'rgba(255, 255, 255, 0.04)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '5px 10px',
              gap: '6px'
            }}>
              <Search size={14} color="var(--text-subtle)" />
              <input
                type="text"
                placeholder="Search user or email..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                style={{ background: 'transparent', border: 'none', color: '#ffffff', fontSize: '12px', width: '160px' }}
              />
            </div>
          </div>
        )}
      </div>

      {/* ================= TAB 1: USERS LIST ================= */}
      {activeTab === 'users' && (
        <div style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-medium)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ background: 'rgba(255, 255, 255, 0.03)', borderBottom: '1px solid var(--border-medium)', textAlign: 'left' }}>
                <th style={{ padding: '12px 18px', color: '#94a3b8', fontWeight: 600 }}>User Identity</th>
                <th style={{ padding: '12px 18px', color: '#94a3b8', fontWeight: 600 }}>Role</th>
                <th style={{ padding: '12px 18px', color: '#94a3b8', fontWeight: 600 }}>Status</th>
                <th style={{ padding: '12px 18px', color: '#94a3b8', fontWeight: 600 }}>Registered</th>
                <th style={{ padding: '12px 18px', color: '#94a3b8', fontWeight: 600 }}>Last Login</th>
                <th style={{ padding: '12px 18px', color: '#94a3b8', fontWeight: 600, textAlign: 'right' }}>Authorization Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((u, idx) => {
                const isSelf = u.id === currentUser.id;
                return (
                  <tr
                    key={u.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      background: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)'
                    }}
                  >
                    <td style={{ padding: '12px 18px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '32px',
                          height: '32px',
                          borderRadius: '50%',
                          background: u.role === 'admin' ? 'var(--gradient-brand)' : 'rgba(255, 255, 255, 0.08)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '12px',
                          fontWeight: 700,
                          color: '#ffffff'
                        }}>
                          {u.username.slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, color: '#ffffff' }}>
                            {u.username} {isSelf && <span style={{ color: 'var(--accent-teal)', fontSize: '11px' }}>(You)</span>}
                          </div>
                          <div style={{ fontSize: '11px', color: 'var(--text-subtle)' }}>{u.email}</div>
                        </div>
                      </div>
                    </td>

                    <td style={{ padding: '12px 18px' }}>
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        fontSize: '11px',
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 600,
                        background: u.role === 'admin' ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255, 255, 255, 0.04)',
                        color: u.role === 'admin' ? '#a5b4fc' : '#94a3b8',
                        border: '1px solid',
                        borderColor: u.role === 'admin' ? 'rgba(99, 102, 241, 0.3)' : 'transparent'
                      }}>
                        {u.role === 'admin' ? 'ADMIN' : 'USER'}
                      </span>
                    </td>

                    <td style={{ padding: '12px 18px' }}>
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        fontSize: '11px',
                        fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                        background: 
                          u.status === 'approved' ? 'rgba(16, 185, 129, 0.12)' :
                          u.status === 'pending' ? 'rgba(245, 158, 11, 0.12)' :
                          'rgba(244, 63, 94, 0.12)',
                        color:
                          u.status === 'approved' ? 'var(--accent-emerald)' :
                          u.status === 'pending' ? 'var(--accent-amber)' :
                          'var(--accent-rose)',
                        border: '1px solid',
                        borderColor:
                          u.status === 'approved' ? 'rgba(16, 185, 129, 0.3)' :
                          u.status === 'pending' ? 'rgba(245, 158, 11, 0.3)' :
                          'rgba(244, 63, 94, 0.3)'
                      }}>
                        {u.status.toUpperCase()}
                      </span>
                    </td>

                    <td style={{ padding: '12px 18px', color: 'var(--text-subtle)', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : 'N/A'}
                    </td>

                    <td style={{ padding: '12px 18px', color: 'var(--text-subtle)', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}
                    </td>

                    <td style={{ padding: '12px 18px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                        {/* Pending approval controls */}
                        {u.status === 'pending' && (
                          <>
                            <button
                              onClick={() => handleUpdateStatus(u.id, 'approved')}
                              style={{
                                padding: '4px 10px',
                                borderRadius: 'var(--radius-sm)',
                                background: 'rgba(16, 185, 129, 0.2)',
                                border: '1px solid rgba(16, 185, 129, 0.4)',
                                color: '#a7f3d0',
                                fontSize: '11px',
                                fontWeight: 600,
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px'
                              }}
                            >
                              <Check size={12} /> Approve
                            </button>
                            <button
                              onClick={() => handleUpdateStatus(u.id, 'rejected')}
                              style={{
                                padding: '4px 10px',
                                borderRadius: 'var(--radius-sm)',
                                background: 'rgba(244, 63, 94, 0.15)',
                                border: '1px solid rgba(244, 63, 94, 0.3)',
                                color: '#fecdd3',
                                fontSize: '11px',
                                fontWeight: 600,
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px'
                              }}
                            >
                              <X size={12} /> Reject
                            </button>
                          </>
                        )}

                        {/* Deactivate / Reactivate for approved/deactivated */}
                        {u.status === 'approved' && !isSelf && (
                          <button
                            onClick={() => handleUpdateStatus(u.id, 'deactivated')}
                            style={{
                              padding: '4px 8px',
                              borderRadius: 'var(--radius-sm)',
                              background: 'rgba(244, 63, 94, 0.1)',
                              border: '1px solid rgba(244, 63, 94, 0.25)',
                              color: '#fda4af',
                              fontSize: '11px'
                            }}
                          >
                            Deactivate
                          </button>
                        )}

                        {u.status === 'deactivated' && (
                          <button
                            onClick={() => handleUpdateStatus(u.id, 'approved')}
                            style={{
                              padding: '4px 8px',
                              borderRadius: 'var(--radius-sm)',
                              background: 'rgba(16, 185, 129, 0.15)',
                              border: '1px solid rgba(16, 185, 129, 0.3)',
                              color: '#a7f3d0',
                              fontSize: '11px'
                            }}
                          >
                            Reactivate
                          </button>
                        )}

                        {/* Role Switcher */}
                        {!isSelf && (
                          <button
                            onClick={() => handleUpdateRole(u.id, u.role === 'admin' ? 'user' : 'admin')}
                            style={{
                              padding: '4px 8px',
                              borderRadius: 'var(--radius-sm)',
                              background: 'rgba(255, 255, 255, 0.05)',
                              border: '1px solid var(--border-subtle)',
                              color: 'var(--text-muted)',
                              fontSize: '11px'
                            }}
                          >
                            {u.role === 'admin' ? 'Demote to User' : 'Make Admin'}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ================= TAB 2: AUDIT LOGS ================= */}
      {activeTab === 'audit' && (
        <div style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-medium)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden'
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ background: 'rgba(255, 255, 255, 0.03)', borderBottom: '1px solid var(--border-medium)', textAlign: 'left' }}>
                <th style={{ padding: '10px 16px', color: '#94a3b8' }}>Event Type</th>
                <th style={{ padding: '10px 16px', color: '#94a3b8' }}>Actor / Target</th>
                <th style={{ padding: '10px 16px', color: '#94a3b8' }}>IP Address</th>
                <th style={{ padding: '10px 16px', color: '#94a3b8' }}>Event Details</th>
                <th style={{ padding: '10px 16px', color: '#94a3b8' }}>Timestamp (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map((log) => (
                <tr key={log.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '10px 16px' }}>
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 600,
                      fontSize: '11px',
                      color: log.event_type.includes('FAILURE') || log.event_type.includes('DEACTIVATED') 
                        ? 'var(--accent-rose)' 
                        : log.event_type.includes('APPROVED') || log.event_type.includes('SUCCESS')
                        ? 'var(--accent-emerald)'
                        : 'var(--accent-primary)'
                    }}>
                      {log.event_type}
                    </span>
                  </td>
                  <td style={{ padding: '10px 16px', color: 'var(--text-muted)' }}>
                    {log.actor_id ? log.actor_id.slice(0, 8) : 'SYSTEM'} 
                    {log.target_user_id && ` → ${log.target_user_id.slice(0, 8)}`}
                  </td>
                  <td style={{ padding: '10px 16px', fontFamily: 'var(--font-mono)', color: 'var(--text-subtle)' }}>
                    {log.ip_address || 'unknown'}
                  </td>
                  <td style={{ padding: '10px 16px', color: '#e2e8f0' }}>
                    {log.details || '—'}
                  </td>
                  <td style={{ padding: '10px 16px', fontFamily: 'var(--font-mono)', color: 'var(--text-subtle)' }}>
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal: Admin Provision User */}
      {showCreateModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100
        }}>
          <div style={{
            width: '100%',
            maxWidth: '440px',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-medium)',
            borderRadius: 'var(--radius-xl)',
            padding: '24px'
          }}>
            <h3 style={{ fontSize: '16px', color: '#ffffff', marginBottom: '16px' }}>
              Provision New User Account
            </h3>
            <form onSubmit={handleCreateUser} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Username</label>
                <input
                  type="text"
                  required
                  value={newUsername}
                  onChange={e => setNewUsername(e.target.value)}
                  style={{ width: '100%', padding: '8px 10px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-sm)', color: '#ffffff', marginTop: '4px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Email</label>
                <input
                  type="email"
                  required
                  value={newEmail}
                  onChange={e => setNewEmail(e.target.value)}
                  style={{ width: '100%', padding: '8px 10px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-sm)', color: '#ffffff', marginTop: '4px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Password (min 8 chars)</label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  style={{ width: '100%', padding: '8px 10px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-sm)', color: '#ffffff', marginTop: '4px' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Role</label>
                  <select
                    value={newRole}
                    onChange={e => setNewRole(e.target.value)}
                    style={{ width: '100%', padding: '8px', background: '#0f1422', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-sm)', color: '#ffffff', marginTop: '4px' }}
                  >
                    <option value="user">User</option>
                    <option value="admin">Administrator</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Status</label>
                  <select
                    value={newStatus}
                    onChange={e => setNewStatus(e.target.value)}
                    style={{ width: '100%', padding: '8px', background: '#0f1422', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-sm)', color: '#ffffff', marginTop: '4px' }}
                  >
                    <option value="approved">Approved</option>
                    <option value="pending">Pending</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  style={{ padding: '8px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createLoading}
                  style={{ padding: '8px 18px', borderRadius: 'var(--radius-sm)', background: 'var(--gradient-brand)', color: '#ffffff', fontWeight: 600 }}
                >
                  {createLoading ? 'Creating...' : 'Provision'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
