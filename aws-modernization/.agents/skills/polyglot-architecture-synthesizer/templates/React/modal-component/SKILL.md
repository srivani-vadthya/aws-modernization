---
name: modal-component
description: "Modal component with focus trap, Escape key handler, backdrop, slots pattern for header/footer/actions, CSS variable tokens"
tags: ["modal", "dialog", "popup", "overlay", "confirm", "uibModal", "$modal", "open", "close"]
trigger: modal
---

# Modal Component — Golden Pattern

## When to Apply
Whenever legacy code uses `$uibModal`, `$modal`, `ng-show` for an overlay, or any dialog/popup pattern.

## Exact Golden Pattern

```tsx
// filepath: src/common/components/Modal/Modal.tsx
import React, { useEffect, useRef } from 'react';

export interface BackdropProps {
  className?: string;
}

export interface ModalProps {
  id?: string;
  isOpen?: boolean;
  onClose?: (event?: unknown) => void;
  children?: React.ReactNode;
  disableEscapeKeyDown?: boolean;
  hideBackdrop?: boolean;
  BackdropProps?: BackdropProps;
  className?: string;
  title?: React.ReactNode;
  slots?: Record<string, React.ReactNode>;  // ← header | footer | actions slots
  maxWidth?: string;
  maxHeight?: string;
  'aria-label'?: string;
  'aria-labelledby'?: string;
  'aria-describedby'?: string;
  'aria-modal'?: boolean;
  'aria-live'?: 'off' | 'polite' | 'assertive';
}

const Modal: React.FC<ModalProps> = ({
  id, isOpen = false, onClose, children,
  disableEscapeKeyDown = false, hideBackdrop = false, BackdropProps,
  className = '', title, slots,
  maxWidth = '600px', maxHeight = '80vh',
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
  'aria-describedby': ariaDescribedby,
  'aria-modal': ariaModal = true,
  'aria-live': ariaLive = 'polite',
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Escape key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !disableEscapeKeyDown && isOpen) onClose?.(undefined);
    };
    if (isOpen) {
      globalThis.addEventListener('keydown', handleKeyDown);
      return () => globalThis.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, disableEscapeKeyDown, onClose]);

  // Focus trap — move focus into modal when it opens
  useEffect(() => {
    if (isOpen && containerRef.current) containerRef.current.focus();
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      id={id}
      style={{
        position: 'fixed', inset: 0,
        zIndex: parseInt(getComputedStyle(document.documentElement).getPropertyValue('--z-modal')) || 1050,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      {/* Backdrop */}
      {!hideBackdrop && (
        <button
          type="button" aria-label="close modal"
          onClick={() => onClose?.(undefined)}
          style={{ position: 'absolute', inset: 0, backgroundColor: 'var(--overlay-backdrop)', cursor: 'pointer' }}
          className={BackdropProps?.className}
        />
      )}

      {/* Dialog */}
      <div
        ref={containerRef}
        role="dialog"
        aria-label={ariaLabel} aria-labelledby={ariaLabelledby}
        aria-describedby={ariaDescribedby} aria-modal={ariaModal} aria-live={ariaLive}
        tabIndex={-1}
        style={{
          position: 'relative', zIndex: 10,
          width: '100%', maxWidth, maxHeight,
          padding: 'var(--space-6)',
          backgroundColor: 'var(--bg-surface)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-lg)',
          outline: 'none', overflowY: 'auto',
        }}
        className={className}
      >
        {/* Header slot or title */}
        {slots?.header ?? (title ? (
          <div style={{ marginBottom: 'var(--space-4)', fontWeight: 'var(--font-weight-semibold)', fontSize: 'var(--font-size-lg)', color: 'var(--text-primary)' }}>
            {title}
          </div>
        ) : null)}

        {/* Body */}
        <div style={{ color: 'var(--text-primary)', lineHeight: 'var(--line-height-normal)' }}>
          {children}
        </div>

        {/* Footer slot */}
        {slots?.footer && <div style={{ marginTop: 'var(--space-6)' }}>{slots.footer}</div>}

        {/* Actions slot */}
        {slots?.actions && <div style={{ marginTop: 'var(--space-4)' }}>{slots.actions}</div>}

        {/* Close button */}
        {onClose && (
          <button
            type="button" aria-label="close modal"
            onClick={() => onClose?.(undefined)}
            style={{
              position: 'absolute', top: 'var(--space-4)', right: 'var(--space-4)',
              backgroundColor: 'transparent', border: 'none',
              fontSize: 'var(--font-size-2xl)', color: 'var(--text-secondary)',
              cursor: 'pointer', outline: 'none',
            }}
          >
            &times;
          </button>
        )}
      </div>
    </div>
  );
};

export default Modal;
```

## Usage Pattern (in a page)
```tsx
const [isOpen, setIsOpen] = useState(false);

<Modal
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  title="Confirm Action"
  slots={{
    actions: (
      <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'flex-end' }}>
        <Button variant="outlined" onClick={() => setIsOpen(false)}>Cancel</Button>
        <Button variant="contained" color="error" onClick={handleConfirm}>Delete</Button>
      </div>
    )
  }}
>
  Are you sure you want to delete this item?
</Modal>
```
