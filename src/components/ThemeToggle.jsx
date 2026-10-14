import React from 'react';
import { Sun, Moon } from 'lucide-react';

/**
 * Sun/Moon toggle button. Works in both Header and standalone positions.
 * Calls onToggle(currentTheme) → parent updates state.
 */
export default function ThemeToggle({ theme, onToggle, size = 'md' }) {
  const isLight = theme === 'light';
  const dim = size === 'sm' ? 28 : 34;
  const iconSize = size === 'sm' ? 14 : 16;

  return (
    <button
      onClick={onToggle}
      aria-label={isLight ? 'Switch to Night Mode' : 'Switch to Light Mode'}
      title={isLight ? 'Switch to Night Mode' : 'Switch to Light Mode'}
      style={{
        width:  `${dim}px`,
        height: `${dim}px`,
        borderRadius: 'var(--radius-md)',
        background: isLight
          ? 'rgba(0,0,0,0.06)'
          : 'rgba(255,255,255,0.07)',
        border: '1px solid var(--border-medium)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'all var(--transition-fast)',
        flexShrink: 0,
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = 'var(--accent-muted)';
        e.currentTarget.style.borderColor = 'var(--accent-primary)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = isLight
          ? 'rgba(0,0,0,0.06)'
          : 'rgba(255,255,255,0.07)';
        e.currentTarget.style.borderColor = 'var(--border-medium)';
      }}
    >
      {isLight
        ? <Moon  size={iconSize} color="var(--text-secondary)" />
        : <Sun   size={iconSize} color="var(--accent-light)" />
      }
    </button>
  );
}
