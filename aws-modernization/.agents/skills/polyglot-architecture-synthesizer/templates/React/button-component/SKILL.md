---
name: button-component
description: "Button component with forwardRef, variant/color/size token maps, hover/focus state handlers via CSS variables"
tags: ["button", "form", "submit", "click", "action", "cta", "interactive"]
trigger: button
---

# Button Component — Golden Pattern

## When to Apply
Any time an interactive button, submit, or action element is needed. Never write raw `<button>` — always use or mirror this pattern.

## Exact Golden Pattern

```tsx
// filepath: src/common/components/Button/Button.tsx
import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'contained' | 'outlined' | 'text';
  color?: 'primary' | 'secondary' | 'success' | 'error' | 'info' | 'warning' | 'inherit';
  size?: 'small' | 'medium' | 'large';
  fullWidth?: boolean;
  startIcon?: React.ReactNode;
  endIcon?: React.ReactNode;
  disableElevation?: boolean;
  ariaLabel?: string;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({
    variant = 'contained', color = 'primary', size = 'medium',
    fullWidth = false, startIcon, endIcon, disableElevation = false,
    disabled = false, ariaLabel, children, className = '',
    onClick, onMouseEnter, onMouseLeave, onFocus, onBlur, ...rest
  }, ref) => {

    const colorMap: Record<string, { base: string; hover: string; light: string }> = {
      primary:   { base: 'var(--color-primary)',   hover: 'var(--color-primary-hover)', light: 'var(--color-gray-50)' },
      secondary: { base: 'var(--color-secondary)', hover: 'var(--color-gray-600)',      light: 'var(--color-gray-50)' },
      success:   { base: 'var(--color-success)',   hover: 'var(--color-gray-700)',      light: 'var(--color-gray-50)' },
      error:     { base: 'var(--color-error)',     hover: 'var(--color-gray-700)',      light: 'var(--color-gray-50)' },
    };
    const sizeMap: Record<string, { padding: string; height: string; fontSize: string }> = {
      small:  { padding: 'var(--space-2) var(--space-3)', height: 'var(--control-height-sm)', fontSize: 'var(--font-size-sm)' },
      medium: { padding: 'var(--space-3) var(--space-4)', height: 'var(--control-height-md)', fontSize: 'var(--font-size-md)' },
      large:  { padding: 'var(--space-4) var(--space-6)', height: 'var(--control-height-lg)', fontSize: 'var(--font-size-lg)' },
    };

    const tokens = colorMap[color] || colorMap.primary;
    const sizes  = sizeMap[size] || sizeMap.medium;

    const baseStyle: React.CSSProperties = {
      fontWeight: 'var(--font-weight-medium)',
      borderRadius: 'var(--radius-md)',
      transition: 'all var(--transition-normal)',
      cursor: disabled ? 'var(--cursor-disabled)' : 'pointer',
      opacity: disabled ? 'var(--opacity-disabled)' : 1,
      padding: sizes.padding, height: sizes.height, fontSize: sizes.fontSize,
      width: fullWidth ? '100%' : 'auto',
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      gap: 'var(--space-2)',
      ...(variant === 'contained' ? {
        backgroundColor: disabled ? 'var(--bg-muted)' : tokens.base,
        color: disabled ? 'var(--text-muted)' : 'var(--text-inverse)',
        border: 'none',
        boxShadow: disableElevation ? 'none' : 'var(--shadow-sm)',
      } : variant === 'outlined' ? {
        backgroundColor: 'transparent',
        color: disabled ? 'var(--text-muted)' : tokens.base,
        border: `var(--border-width-sm) solid ${disabled ? 'var(--border-color)' : tokens.base}`,
      } : {
        backgroundColor: 'transparent',
        color: disabled ? 'var(--text-muted)' : tokens.base,
        border: 'none',
      }),
    };

    return (
      <button
        ref={ref} type="button" disabled={disabled}
        aria-label={ariaLabel} style={baseStyle} className={className}
        onClick={onClick}
        onMouseEnter={e => { if (!disabled && variant === 'contained') (e.currentTarget as HTMLButtonElement).style.backgroundColor = tokens.hover; onMouseEnter?.(e); }}
        onMouseLeave={e => { if (!disabled && variant === 'contained') (e.currentTarget as HTMLButtonElement).style.backgroundColor = tokens.base; onMouseLeave?.(e); }}
        onFocus={e => { if (!disabled) (e.currentTarget as HTMLButtonElement).style.boxShadow = 'var(--focus-ring)'; onFocus?.(e); }}
        onBlur={e => { if (!disabled) (e.currentTarget as HTMLButtonElement).style.boxShadow = variant === 'contained' && !disableElevation ? 'var(--shadow-sm)' : 'none'; onBlur?.(e); }}
        {...rest}
      >
        {startIcon && <span style={{ display: 'flex', alignItems: 'center' }}>{startIcon}</span>}
        <span>{children}</span>
        {endIcon && <span style={{ display: 'flex', alignItems: 'center' }}>{endIcon}</span>}
      </button>
    );
  }
);
Button.displayName = 'Button';
export default Button;
```

## Rules
1. Always `forwardRef`
2. Always use CSS variable tokens (`var(--color-primary)`) — never hardcoded hex colors
3. `colorMap` and `sizeMap` as lookup tables — never inline conditions
4. Hover/focus via `onMouseEnter`/`onFocus` inline style mutation — NOT CSS class toggling
