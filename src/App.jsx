import React, { useState, useEffect, useCallback } from 'react';
import { Loader2 } from 'lucide-react';

import Header from './components/Header';
import Sidebar from './components/Sidebar';
import AiCopilot from './components/AiCopilot';
import DocumentPanel from './components/DocumentPanel';
import UploadModal from './components/UploadModal';
import AdminDashboard from './components/AdminDashboard';
import AuthView from './components/AuthView';
import { PendingScreen, AccessDeniedScreen } from './components/AccountStatusScreens';

import { auth as authApi, conversations as convsApi, documents as docsApi, setApiCsrfToken, setOnUnauthorized } from './utils/api';
import { getInitialTheme, applyTheme, toggleTheme } from './utils/theme';

// Apply theme before first paint (avoids flash)
applyTheme(getInitialTheme());

export default function App() {
  // ── Theme ──────────────────────────────────────────────────────────────────
  const [theme, setTheme] = useState(getInitialTheme);

  const handleToggleTheme = () => {
    setTheme(cur => {
      const next = toggleTheme(cur);  // toggleTheme also calls applyTheme
      return next;
    });
  };

  // ── Auth ───────────────────────────────────────────────────────────────────
  const [authLoading, setAuthLoading]   = useState(true);
  const [currentUser, setCurrentUser]   = useState(null);
  const [csrfToken,   setCsrfToken]     = useState(null);
  const [currentView, setCurrentView]   = useState('workspace');

  // Keep the API module's CSRF token in sync
  useEffect(() => {
    setApiCsrfToken(csrfToken);
  }, [csrfToken]);

  // Wire up global 401 handler
  useEffect(() => {
    setOnUnauthorized(() => {
      setCurrentUser(null);
      setCsrfToken(null);
      setConversations([]);
      setActiveConvId(null);
    });
  }, []);

  const verifySession = useCallback(async () => {
    try {
      const data = await authApi.me();
      if (data.authenticated && data.user) {
        setCurrentUser(data.user);
        setCsrfToken(data.csrf_token);
        setApiCsrfToken(data.csrf_token);
        setCurrentView(data.user.role === 'admin' ? 'admin' : 'workspace');
      } else {
        setCurrentUser(null);
      }
    } catch {
      setCurrentUser(null);
    } finally {
      setAuthLoading(false);
    }
  }, []);

  useEffect(() => { verifySession(); }, [verifySession]);

  const handleAuthSuccess = (user, token) => {
    setCurrentUser(user);
    setCsrfToken(token);
    setApiCsrfToken(token);
    setCurrentView(user.role === 'admin' && user.status === 'approved' ? 'admin' : 'workspace');
  };

  const handleLogout = async () => {
    try { await authApi.logout(); } catch { /* ignore */ }
    setCurrentUser(null);
    setCsrfToken(null);
    setApiCsrfToken(null);
    setConversations([]);
    setActiveConvId(null);
    setMessages([]);
    setDocuments([]);
    setCurrentView('workspace');
  };

  // ── Conversations ─────────────────────────────────────────────────────────
  const [conversations,  setConversations]  = useState([]);
  const [activeConvId,   setActiveConvId]   = useState(null);
  const [convsLoading,   setConvsLoading]   = useState(false);
  const [isSidebarOpen,  setIsSidebarOpen]  = useState(true);

  // ── Messages for active conversation ──────────────────────────────────────
  const [messages,       setMessages]       = useState([]);
  const [messagesLoading,setMessagesLoading]= useState(false);
  const [isSending,      setIsSending]      = useState(false);

  // ── Documents for active conversation ─────────────────────────────────────
  const [documents,      setDocuments]      = useState([]);
  const [isUploadOpen,   setIsUploadOpen]   = useState(false);

  // ── Load conversations list ────────────────────────────────────────────────
  const loadConversations = useCallback(async () => {
    if (!currentUser) return;
    setConvsLoading(true);
    try {
      const data = await convsApi.list();
      setConversations(data);
    } catch { /* ignore */ }
    finally { setConvsLoading(false); }
  }, [currentUser]);

  useEffect(() => {
    if (currentUser?.status === 'approved') loadConversations();
  }, [currentUser, loadConversations]);

  // ── Load messages for active conversation ─────────────────────────────────
  const loadMessages = useCallback(async (convId) => {
    if (!convId) return;
    setMessagesLoading(true);
    try {
      const data = await convsApi.messages(convId);
      setMessages(data);
    } catch { setMessages([]); }
    finally { setMessagesLoading(false); }
  }, []);

  // ── Load documents for active conversation ────────────────────────────────
  const loadDocuments = useCallback(async (convId) => {
    if (!convId) return;
    try {
      const data = await docsApi.list(convId);
      setDocuments(data.documents || []);
    } catch { setDocuments([]); }
  }, []);

  // When active conversation changes, load its messages and documents
  useEffect(() => {
    if (activeConvId) {
      loadMessages(activeConvId);
      loadDocuments(activeConvId);
    } else {
      setMessages([]);
      setDocuments([]);
    }
  }, [activeConvId, loadMessages, loadDocuments]);

  // ── Conversation actions ──────────────────────────────────────────────────
  const handleSelectConversation = (convId) => {
    setActiveConvId(convId);
  };

  const handleCreateConversation = async () => {
    try {
      const conv = await convsApi.create({ title: 'New conversation' });
      setConversations(prev => [conv, ...prev]);
      setActiveConvId(conv.id);
    } catch (err) {
      console.error('Create conversation failed:', err.message);
    }
  };

  const handleRenameConversation = async (convId, newTitle) => {
    try {
      const updated = await convsApi.rename(convId, newTitle);
      setConversations(prev =>
        prev.map(c => c.id === convId ? { ...c, title: updated.title } : c)
      );
    } catch (err) {
      console.error('Rename failed:', err.message);
    }
  };

  const handleDeleteConversation = async (convId) => {
    await convsApi.delete(convId);
    setConversations(prev => prev.filter(c => c.id !== convId));
    if (activeConvId === convId) {
      setActiveConvId(null);
    }
  };

  // ── Ask question ──────────────────────────────────────────────────────────
  const handleSendQuestion = async (question) => {
    if (!activeConvId || isSending) return;
    setIsSending(true);

    // Optimistically add user message for immediate feedback
    const tempId = `temp-${Date.now()}`;
    setMessages(prev => [...prev, {
      id: tempId,
      conversation_id: activeConvId,
      role: 'user',
      content: question,
      created_at: new Date().toISOString(),
      citations: [],
    }]);

    try {
      const res = await convsApi.ask(activeConvId, question);

      // Replace temp message + add real answer
      await loadMessages(activeConvId);

      // If the conversation was auto-titled, update the list
      if (res.conversation_title) {
        setConversations(prev =>
          prev.map(c => c.id === activeConvId
            ? { ...c, title: res.conversation_title, updated_at: new Date().toISOString() }
            : c
          )
        );
      }

      // Re-sort conversations by updated_at
      setConversations(prev => [...prev].sort(
        (a, b) => new Date(b.updated_at) - new Date(a.updated_at)
      ));
    } catch (err) {
      // Replace temp message with error
      setMessages(prev => prev.map(m => m.id === tempId
        ? { ...m, role: 'user', content: question }
        : m
      ).concat({
        id: `err-${Date.now()}`,
        conversation_id: activeConvId,
        role: 'assistant',
        content: `[Error] ${err.message}`,
        created_at: new Date().toISOString(),
        citations: [],
      }));
    } finally {
      setIsSending(false);
    }
  };

  // ── Upload complete → refresh docs ────────────────────────────────────────
  const handleUploadComplete = () => {
    if (activeConvId) {
      loadDocuments(activeConvId);
      loadConversations();
    }
  };

  // ── Active conversation object ────────────────────────────────────────────
  const activeConversation = conversations.find(c => c.id === activeConvId) || null;

  // ── Render: loading ───────────────────────────────────────────────────────
  if (authLoading) {
    return (
      <div style={{
        width: '100vw', height: '100vh',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg-primary)',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
          <Loader2 size={28} className="animate-spin-slow" color="var(--accent-primary)" />
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Verifying session…</span>
        </div>
      </div>
    );
  }

  // ── Render: unauthenticated ────────────────────────────────────────────────
  if (!currentUser) {
    return <AuthView onAuthSuccess={handleAuthSuccess} theme={theme} onToggleTheme={handleToggleTheme} />;
  }

  // ── Render: pending ────────────────────────────────────────────────────────
  if (currentUser.status === 'pending') {
    return <PendingScreen user={currentUser} onCheckStatus={verifySession} onLogout={handleLogout} />;
  }

  // ── Render: deactivated / rejected ────────────────────────────────────────
  if (currentUser.status === 'deactivated' || currentUser.status === 'rejected') {
    return <AccessDeniedScreen user={currentUser} onLogout={handleLogout} />;
  }

  // ── Render: admin dashboard ────────────────────────────────────────────────
  if (currentView === 'admin' && currentUser.role === 'admin') {
    return (
      <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)', overflow: 'hidden' }}>
        <Header
          currentUser={currentUser}
          currentView={currentView}
          onSwitchView={setCurrentView}
          onLogout={handleLogout}
          theme={theme}
          onToggleTheme={handleToggleTheme}
        />
        <AdminDashboard
          currentUser={currentUser}
          csrfToken={csrfToken}
          onSwitchToWorkspace={() => setCurrentView('workspace')}
          theme={theme}
          onToggleTheme={handleToggleTheme}
        />
      </div>
    );
  }

  // ── Render: user workspace ─────────────────────────────────────────────────
  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)', overflow: 'hidden' }}>
      <Header
        currentUser={currentUser}
        currentView={currentView}
        onSwitchView={setCurrentView}
        onLogout={handleLogout}
        onOpenUpload={() => {
          if (!activeConvId) handleCreateConversation().then(() => setIsUploadOpen(true));
          else setIsUploadOpen(true);
        }}
        theme={theme}
        onToggleTheme={handleToggleTheme}
        activeConversation={activeConversation}
      />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Sidebar — conversation history */}
        <Sidebar
          conversations={conversations}
          activeConvId={activeConvId}
          onSelectConversation={handleSelectConversation}
          onCreateConversation={handleCreateConversation}
          onRenameConversation={handleRenameConversation}
          onDeleteConversation={handleDeleteConversation}
          isOpen={isSidebarOpen}
          onToggle={() => setIsSidebarOpen(o => !o)}
          loading={convsLoading}
        />

        {/* Main workspace */}
        <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          {!activeConvId ? (
            /* Empty state — no conversation selected */
            <EmptyWorkspace onNewConversation={handleCreateConversation} />
          ) : (
            <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
              {/* Center: Document panel + info */}
              <div style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                padding: '16px',
                gap: '12px',
                minWidth: 0,
              }}>
                {/* Document management panel */}
                <DocumentPanel
                  conversationId={activeConvId}
                  documents={documents}
                  onRefresh={() => loadDocuments(activeConvId)}
                  onOpenUpload={() => setIsUploadOpen(true)}
                />

                {/* Loading indicator for messages */}
                {messagesLoading && (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '20px' }}>
                    <Loader2 size={18} className="animate-spin-slow" color="var(--text-muted)" />
                  </div>
                )}
              </div>

              {/* Right: Chat panel */}
              <AiCopilot
                conversationId={activeConvId}
                messages={messages}
                documents={documents}
                onSendQuestion={handleSendQuestion}
                isSending={isSending}
              />
            </div>
          )}
        </main>
      </div>

      {/* Upload modal */}
      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        conversationId={activeConvId}
        onUploadComplete={handleUploadComplete}
      />
    </div>
  );
}

/* ── Empty workspace ── */
function EmptyWorkspace({ onNewConversation }) {
  return (
    <div style={{
      flex: 1,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '40px 20px', textAlign: 'center',
      gap: '20px',
    }}>
      <div style={{
        width: '64px', height: '64px', borderRadius: '18px',
        background: 'var(--gradient-brand)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: 'var(--shadow-glow)',
      }}>
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
      </div>

      <div>
        <h2 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
          Welcome to <span style={{
            background: 'var(--gradient-brand)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>DocuMind</span>
        </h2>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: 1.6, maxWidth: '400px' }}>
          Chat intelligently with your PDF documents. Upload files, ask questions,
          and get grounded answers with precise source citations.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxWidth: '340px', width: '100%' }}>
        <button
          onClick={onNewConversation}
          className="btn-primary"
          style={{ justifyContent: 'center', padding: '12px 24px', fontSize: '14px' }}
        >
          Start a new conversation
        </button>
        <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          Or select an existing conversation from the sidebar.
        </p>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px',
        maxWidth: '520px', width: '100%', marginTop: '8px',
      }}>
        {[
          { icon: '📄', title: 'Upload PDFs', desc: 'Add multiple documents to one conversation' },
          { icon: '🔍', title: 'Ask questions', desc: 'Get precise answers grounded in your files' },
          { icon: '📌', title: 'Cited answers', desc: 'Every answer references the exact page' },
        ].map(({ icon, title, desc }) => (
          <div key={title} style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            padding: '16px',
            textAlign: 'center',
          }}>
            <span style={{ fontSize: '24px' }}>{icon}</span>
            <p style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '8px' }}>{title}</p>
            <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', lineHeight: 1.4 }}>{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
