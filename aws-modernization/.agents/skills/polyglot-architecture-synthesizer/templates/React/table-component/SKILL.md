---
name: table-component
description: "Generic typed Table component with Louvain sort state, renderCell override, stickyHeader, aria attributes, and CSS variable tokens"
tags: ["table", "grid", "list", "data", "ng-repeat", "repeat", "rows", "columns", "sort", "paginate"]
trigger: data_table
---

# Table Component — Golden Pattern

## When to Apply
Whenever legacy code has `ng-repeat` over a collection, `gridOptions`, or renders a list as a table/grid.

## Exact Golden Pattern

```tsx
// filepath: src/common/components/Table/Table.tsx
import React, { useMemo, useState } from 'react';

export type TableSize = 'sm' | 'md' | 'lg';
export type TableVariant = 'standard' | 'striped' | 'outlined';

export interface TableColumn<T> {
  id?: string;
  field: keyof T | string;
  headerName?: string;
  align?: 'left' | 'center' | 'right';
  width?: string | number;
  sortable?: boolean;
  renderCell?: (row: T) => React.ReactNode;  // ← custom cell renderer
  tooltip?: React.ReactNode;
  className?: string;
  hide?: boolean;
}

export interface TableProps<T> {
  id?: string;
  className?: string;
  size?: TableSize;
  variant?: TableVariant;
  'aria-label'?: string;
  'aria-labelledby'?: string;
  'aria-describedby'?: string;
  'aria-live'?: 'polite' | 'assertive' | 'off';
  columns: TableColumn<T>[];
  rows: T[];
  sortable?: boolean;
  defaultSort?: { field: keyof T | string; order: 'asc' | 'desc' } | null;
  onRowClick?: (row: T) => void;
  stickyHeader?: boolean;
  dense?: boolean;
}

const sizeConfig: Record<TableSize, { padding: string; fontSize: string }> = {
  sm: { padding: 'var(--space-1) var(--space-2)', fontSize: 'var(--font-size-xs)' },
  md: { padding: 'var(--space-2) var(--space-3)', fontSize: 'var(--font-size-sm)' },
  lg: { padding: 'var(--space-3) var(--space-4)', fontSize: 'var(--font-size-md)' },
};

const Table = <T extends Record<string, unknown>>({
  id, className = '', size = 'md', variant = 'standard',
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
  'aria-describedby': ariaDescribedby,
  'aria-live': ariaLive,
  columns = [], rows = [],
  sortable = true, defaultSort = null,
  onRowClick, stickyHeader = false, dense = false,
}: TableProps<T>) => {
  const [sortState, setSortState] = useState<{ field?: string; order?: 'asc' | 'desc' }>(() =>
    defaultSort ? { field: String(defaultSort.field), order: defaultSort.order } : {}
  );

  const handleSort = (field: string) => {
    if (!sortable) return;
    setSortState(prev =>
      prev.field === field
        ? { field, order: prev.order === 'asc' ? 'desc' : 'asc' }
        : { field, order: 'asc' }
    );
  };

  const sortedRows = useMemo(() => {
    if (!sortState.field) return rows;
    return [...rows].sort((a, b) => {
      const av = String(a[sortState.field!] ?? '');
      const bv = String(b[sortState.field!] ?? '');
      return sortState.order === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [rows, sortState]);

  const { padding, fontSize } = sizeConfig[size];
  const visibleColumns = columns.filter(col => !col.hide);

  return (
    <div
      style={{ overflowX: 'auto', width: '100%', border: variant === 'outlined' ? '1px solid var(--border-color)' : 'none', borderRadius: 'var(--radius-md)' }}
      role="region" aria-label={ariaLabel} aria-labelledby={ariaLabelledby}
      aria-describedby={ariaDescribedby} aria-live={ariaLive}
    >
      <table
        id={id}
        className={className}
        style={{ width: '100%', borderCollapse: 'collapse', fontSize }}
        aria-label={ariaLabel}
      >
        <thead style={stickyHeader ? { position: 'sticky', top: 0, zIndex: 1, backgroundColor: 'var(--bg-surface)' } : {}}>
          <tr>
            {visibleColumns.map((col, i) => (
              <th
                key={col.id || String(col.field) || i}
                style={{
                  padding: dense ? 'var(--space-1) var(--space-2)' : padding,
                  textAlign: col.align || 'left',
                  width: col.width,
                  cursor: sortable && col.sortable !== false ? 'pointer' : 'default',
                  userSelect: 'none',
                  fontWeight: 'var(--font-weight-semibold)',
                  color: 'var(--text-secondary)',
                  borderBottom: '2px solid var(--border-color)',
                  whiteSpace: 'nowrap',
                }}
                onClick={() => col.sortable !== false && handleSort(String(col.field))}
                className={col.className}
              >
                {col.headerName ?? String(col.field)}
                {sortState.field === String(col.field) && (
                  <span aria-hidden="true" style={{ marginLeft: 'var(--space-1)' }}>
                    {sortState.order === 'asc' ? '↑' : '↓'}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, ri) => (
            <tr
              key={ri}
              onClick={() => onRowClick?.(row)}
              style={{
                cursor: onRowClick ? 'pointer' : 'default',
                backgroundColor: variant === 'striped' && ri % 2 !== 0 ? 'var(--bg-muted)' : 'var(--bg-surface)',
              }}
            >
              {visibleColumns.map((col, ci) => (
                <td
                  key={col.id || String(col.field) || ci}
                  style={{
                    padding: dense ? 'var(--space-1) var(--space-2)' : padding,
                    textAlign: col.align || 'left',
                    borderBottom: '1px solid var(--border-color)',
                    color: 'var(--text-primary)',
                  }}
                  className={col.className}
                >
                  {col.renderCell ? col.renderCell(row) : String(row[col.field as keyof T] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Table;
```

## Usage Example (in a page)
```tsx
<Table<CustomerRow>
  aria-label="Customer list"
  columns={[
    { field: 'name', headerName: 'Name', sortable: true },
    { field: 'email', headerName: 'Email' },
    { field: 'status', headerName: 'Status',
      renderCell: (row) => <span className={row.status === 'active' ? 'text-green-600' : 'text-red-600'}>{row.status}</span> },
  ]}
  rows={customers}
  onRowClick={(row) => navigate(`/customers/${row.id}`)}
/>
```
