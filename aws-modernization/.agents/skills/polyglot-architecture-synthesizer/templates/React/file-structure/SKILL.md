---
name: file-structure
description: "Canonical React project folder structure, file naming conventions, and barrel export pattern for page-level controllers"
tags: ["page", "controller", "routing", "folder", "structure", "architecture"]
trigger: page_controller
---

# File & Folder Structure — Golden Pattern

## When to Apply
Inject ONLY when the legacy code is a **page-level controller** (i.e., has `$routeProvider`, `$stateProvider`, or is registered as a named Angular controller that maps to a route/view template).

## Canonical Folder Layout

```
src/
├── pages/
│   └── <PageName>/           ← PascalCase, matches controller name without "Controller"
│       ├── <PageName>.tsx    ← The page component
│       └── index.ts          ← Barrel export: export { default } from './<PageName>';
├── common/
│   └── components/
│       └── <ComponentName>/  ← Each component in its own folder
│           ├── <ComponentName>.tsx
│           └── index.ts      ← Barrel export
├── config/
│   └── <pageName>.json       ← lowercase, camelCase — form field config for this page
└── scripts/
    ├── utils.ts              ← deepClone, helpers
    └── validationsService.ts ← validateFormFields
```

## Naming Rules
- Page folders: **PascalCase** (`Login`, `CustomerList`, `OrderDetail`)
- Config files: **camelCase** (`login.json`, `customerList.json`)
- Component folders: **PascalCase**
- Always export via `index.ts` barrel — never import `./Login/Login`; always import `./Login`

## Barrel Export Pattern (index.ts)

```ts
// filepath: src/pages/Login/index.ts
export { default } from './Login';
```

## Router Registration (App.tsx pattern)

```tsx
// filepath: src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Home from './pages/Home';
import MainLayout from './common/MainLayout';

const App = () => (
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />
      <Route element={<MainLayout />}>
        <Route path="/home" element={<Home />} />
      </Route>
    </Routes>
  </BrowserRouter>
);

export default App;
```
