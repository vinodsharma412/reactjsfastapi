# Frontend — `App.jsx`, `routes/`, and Entry Point

## Application Bootstrap Flow

```
index.js
  └── ReactDOM.createRoot().render(<App />)
        └── App.jsx
              ├── <BrowserRouter>      ← React Router context
              │     └── <AuthProvider> ← Auth/menu state context
              │           └── <AppRoutes />  ← Route definitions
              └── global.css           ← CSS variables and styles
```

---

## `src/index.js` — DOM Entry Point

```javascript
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './assets/styles/global.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
```

### What Is `createRoot`?

React 18 introduced `createRoot` (replacing `ReactDOM.render`). It enables:
- **Concurrent Mode** — React can pause, interrupt, and resume rendering
- **Automatic batching** — multiple `setState` calls in a single event are batched

`document.getElementById('root')` finds the `<div id="root">` in `public/index.html`.
React renders the entire app inside this div.

---

## `src/App.jsx` — Root Component

```jsx
import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import AppRoutes from './routes';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
```

### Provider Composition — Context Tree

`App.jsx` provides **two contexts** wrapping the entire application:

**`<BrowserRouter>`** — provides routing context. All child components can use:
- `useNavigate()` — programmatic navigation
- `useLocation()` — current URL path
- `<Link>` and `<Navigate>` components

**`<AuthProvider>`** — provides auth state. All child components can use:
- `useAuth()` — get `{ user, menus, login, logout, isAuthenticated }`

**Order matters:** `AuthProvider` is inside `BrowserRouter` so it could use `useNavigate`
if needed (e.g., redirect to `/login` after logout). If reversed, `AuthProvider` would
not have access to routing context.

---

## `src/utils/constants.js` — Dynamic API URL

```javascript
const apiHost = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
const apiPort = process.env.REACT_APP_API_PORT || '9000';

export const API_URL = process.env.REACT_APP_API_URL
  || `http://${apiHost}:${apiPort}/api/v1`;

export const BACKEND_URL = API_URL.replace('/api/v1', '');
export const TOKEN_KEY = 'access_token';
```

### Why Dynamic API URL?

A hardcoded `http://localhost:9000/api/v1` only works on the developer's machine.
This solution automatically adapts:

```
Local dev:     window.location.hostname = "localhost"     → http://localhost:9000/api/v1
Home network:  window.location.hostname = "192.168.1.100" → http://192.168.1.100:9000/api/v1
Production:    REACT_APP_API_URL=https://api.example.com  → https://api.example.com/api/v1
```

`typeof window !== 'undefined'` — guards against server-side rendering (Next.js).
In a browser, `window` is always defined. In Node.js (SSR), it doesn't exist.

`TOKEN_KEY = 'access_token'` — the key used in `localStorage`. Centralised here so
if you rename it, you change it in one place.

---

## `src/routes/index.jsx` — All Route Definitions

```jsx
function AppRoutes() {
  return (
    <Routes>
      <Route path="/login"        element={<Login />} />
      <Route path="/unauthorized" element={<Unauthorized />} />

      {/* Protected layout wrapper */}
      <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>

        <Route index element={
          <RoleRoute roles={['admin', 'manager', 'viewer']}>
            <Dashboard />
          </RoleRoute>
        } />

        <Route path="stocks" element={
          <RoleRoute roles={['admin', 'manager', 'viewer']}>
            <StockDashboard />
          </RoleRoute>
        } />

        <Route path="settings" element={
          <RoleRoute roles={['admin']}>
            <Settings />
          </RoleRoute>
        } />

      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
```

### Nested Routes — How They Work

React Router v6 uses **nested routes** with the `<Outlet>` component.

```
Route "/"     element=<PrivateRoute><Layout /></PrivateRoute>
  └── Route "stocks"  element=<RoleRoute><StockDashboard /></RoleRoute>
```

`Layout.jsx` renders a `<Outlet />` where child routes render:
```jsx
function Layout() {
  return (
    <div className="app-layout">
      <Sidebar />
      <main>
        <Outlet />   {/* ← Child route renders here */}
      </main>
    </div>
  );
}
```

When user visits `/stocks`:
1. React Router renders `<PrivateRoute>` → checks auth → renders `<Layout>`
2. Inside Layout's `<Outlet>`, renders `<RoleRoute>` → checks role → renders `<StockDashboard>`

The layout (sidebar, header) is rendered once. Only the main content (`<Outlet>`) changes
between routes. This prevents sidebar re-mounting on navigation.

### `<Route path="*">` — 404 Catch-All

```jsx
<Route path="*" element={<Navigate to="/" replace />} />
```

`path="*"` matches any URL that didn't match previous routes. Instead of a 404 page,
redirect to `/`. In a SPA, 404 usually means the user navigated to an unknown route
(not a missing server resource) — redirecting to home is a better UX than a blank error page.

---

## `src/routes/PrivateRoute.jsx` — Authentication Guard

```jsx
function PrivateRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) return <Loader />;                           // Still checking token
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}
```

### The `loading` State — Preventing Flash

When the page first loads, `AuthProvider` checks `localStorage` for a token and
calls `/users/me` to validate it. This takes ~100-200ms.

Without `loading`:
```
1. Page loads → isAuthenticated = false → redirects to /login
2. Token validation completes → isAuthenticated = true → but user is on /login now
```

With `loading = true` during validation:
```
1. Page loads → loading = true → shows <Loader /> (spinner)
2. Token validation completes → loading = false → isAuthenticated = true → renders protected page
```

### `<Navigate to="/login" replace>`

`replace` replaces the current history entry instead of pushing a new one.
Without `replace`: browser back button from /login → goes back to /stocks → redirects to /login again (loop).
With `replace`: browser back button from /login → goes back to the page before /stocks.

---

## `src/routes/RoleRoute.jsx` — Two-Level Authorization

```jsx
function RoleRoute({ children, roles }) {
  const { user, menus, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loader />;
  if (!user) return <Navigate to="/login" replace />;

  // Level 1: Static role check
  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/unauthorized" replace />;
  }

  // Level 2: DB-driven menu permission check
  if (menus.length > 0) {
    const menu = menus.find(m =>
      m.path === location.pathname ||
      location.pathname.startsWith(m.path + '/')
    );
    if (menu && !menu.can_view) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return children;
}
```

### Two Levels of Access Control

**Level 1 — Role check (fast, in-memory):**
```javascript
if (!roles.includes(user.role))  // "admin", "manager", or "viewer"
```
Role comes from the JWT payload, decoded at login. Instant check — no API call.

**Level 2 — Menu permission check (DB-driven, fine-grained):**
```javascript
const menu = menus.find(m => m.path === location.pathname);
if (menu && !menu.can_view)  // DB record says this user cannot view this page
```
Menus loaded from `/menus/my` at login. An admin can grant/revoke per-page access for
specific users. A "manager" might normally access `/reports`, but a specific manager
could have `can_view = false` for that menu — they'd be redirected to `/unauthorized`.

This two-layer design separates:
- **Role** = broad access class (admin can access admin tools)
- **Menu permission** = fine-grained per-page control configured by admins in the UI

### `location.pathname.startsWith(m.path + '/')`

Handles nested routes: if `m.path = "/stocks"`, it also matches `/stocks/detail/TCS.NS`.
Without `startsWith`, navigating to a sub-path would bypass the permission check.

---

## Route Security Flow Diagram

```
User visits /stocks
    │
    ▼
PrivateRoute
    ├── loading? → show <Loader />
    ├── !isAuthenticated? → redirect to /login
    └── authenticated → render <Layout>
            │
            ▼
        RoleRoute roles={['admin','manager','viewer']}
            ├── !user? → redirect to /login
            ├── user.role not in roles? → redirect to /unauthorized
            ├── menu.can_view = false? → redirect to /unauthorized
            └── all checks pass → render <StockDashboard />
```

---

## Interview Questions

**Q: What is the difference between React Router v5 and v6?**

v5: `<Switch>`, `<Route exact>`, `useHistory()`, nested routes need manual setup
v6: `<Routes>`, exact matching by default, `useNavigate()`, nested routes built-in

Key v6 change: `<Outlet />` for nested layouts — child routes render where `<Outlet>` is placed.

**Q: What is a SPA (Single Page Application) and how does React Router work?**

In a traditional website, every link click loads a new HTML page from the server.
In a SPA, the browser loads one HTML file once. React Router intercepts link clicks and
updates the DOM without a full page reload. The URL changes (using `history.pushState`)
but no network request is made — React renders the appropriate component.

**Q: What happens when a user refreshes the browser on `/stocks`?**

The browser makes a GET request to the server for `/stocks`. On a normal server, this
would return 404 (the server only knows about `/`). 

Solutions:
1. Configure the server to return `index.html` for all routes (most common)
2. Use hash routing: `/#/stocks` — only the part before `#` is sent to server
3. CRA's dev server does option 1 automatically in development
