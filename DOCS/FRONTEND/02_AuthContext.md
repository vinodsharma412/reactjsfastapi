# Frontend — `context/AuthContext.jsx` + `services/authService.js`

## What Is This File?

`AuthContext.jsx` is the **global state manager for authentication**.
It stores the logged-in user object, available menus, and loading state.
It provides `login()` and `logout()` functions to any component in the tree.

This is React's **Context API** pattern — data shared across the component tree
without prop drilling.

---

## Full Code With Explanation

```jsx
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authService } from '../services/authService';
import { menuService } from '../services/menuService';

const AuthContext = createContext(null);
```

`createContext(null)` creates a new context object. `null` is the default value used
if a component tries to consume the context outside of `<AuthProvider>`. In practice,
every component that uses `useAuth()` is inside `<AuthProvider>`.

---

## `AuthProvider` Component — State Management

```jsx
export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null);    // null = not logged in
  const [menus,   setMenus]   = useState([]);      // empty = no menus loaded
  const [loading, setLoading] = useState(true);   // true during initial check

  const loadMenus = useCallback(async () => {
    try {
      const res = await menuService.getMyMenus();
      setMenus(res.data);
    } catch {
      setMenus([]);   // Fail silently — menus are non-critical
    }
  }, []);   // No deps = function never recreated
```

### `useCallback` — Why It's Used Here

`loadMenus` is called inside `useEffect`'s dependency array:
```jsx
useEffect(() => {
  ...
  .then(res => { setUser(res.data); return loadMenus(); })
  ...
}, [loadMenus]);   // ← loadMenus in dependency array
```

Without `useCallback`: `loadMenus` is a new function on every render.
New function reference → `useEffect` dependency changed → effect runs again →
calls `authService.getMe()` again → sets state → triggers render → new `loadMenus` → infinite loop.

With `useCallback(fn, [])`: `loadMenus` is the same function reference on every render.
`useEffect` only runs when the reference changes — which it never does (empty deps array).

---

## Initial Auth Check (`useEffect`)

```jsx
useEffect(() => {
  if (authService.isAuthenticated()) {
    authService.getMe()
      .then(res => {
        setUser(res.data);
        return loadMenus();
      })
      .catch(() => authService.logout())
      .finally(() => setLoading(false));
  } else {
    setLoading(false);
  }
}, [loadMenus]);
```

### What Happens on App Start

```
App mounts
    │
    ▼
useEffect runs
    │
    ├── localStorage has token?
    │       │
    │       ├── YES → GET /users/me (validate token)
    │       │         ├── 200 OK → setUser(data) → loadMenus() → setLoading(false)
    │       │         └── 401 → authService.logout() (clear token) → setLoading(false)
    │       │
    │       └── NO → setLoading(false) immediately
    │
    ▼
PrivateRoute checks:
    loading=true → shows <Loader />
    loading=false, user=null → redirects to /login
    loading=false, user=obj → renders protected page
```

**Why call `/users/me` on every page load?**

The token in `localStorage` might be:
- Expired (not caught until decode)
- Revoked (admin deactivated the user)
- Stale (user data changed)

Calling `/users/me` validates the token server-side AND loads fresh user data
(role, name, avatar) in one request.

### `.catch(() => authService.logout())`

If the token is expired or the backend is down:
- `.getMe()` rejects with a 401
- The `catch` calls `logout()` which removes the token from `localStorage`
- `setLoading(false)` still runs (in `finally`)
- `PrivateRoute` sees `isAuthenticated = false` → redirects to `/login`

---

## `login()` Function

```jsx
const login = async (username, password) => {
  await authService.login(username, password);   // POST /auth/token → store token
  const res = await authService.getMe();         // GET /users/me → get user data
  setUser(res.data);                             // Update state
  await loadMenus();                             // Load menus for this user
};
```

Three sequential async operations:
1. **Authenticate** — get JWT token, save to `localStorage`
2. **Load user** — fetch user object (id, username, role, avatar)
3. **Load menus** — fetch this user's accessible menus

All three must succeed for login to be considered complete. If any fails:
- Token is in `localStorage` (from step 1)
- But `user` state is still `null`
- `PrivateRoute` sees `isAuthenticated = !!user` = false
- User stays on login page with the error from step 2 or 3

---

## `logout()` Function

```jsx
const logout = () => {
  authService.logout();    // Remove token from localStorage
  setUser(null);           // Clear user state
  setMenus([]);            // Clear menus state
};
```

After `setUser(null)`:
- `isAuthenticated = !!null = false`
- All `<PrivateRoute>` components redirect to `/login`
- React re-renders automatically

No API call needed to logout — JWT is **stateless**. Removing it from `localStorage`
is sufficient. The token still "works" until it expires, but no client holds it.

For security-critical apps, maintain a **token blacklist** on the server — the backend
checks if a token is in the blacklist before accepting it.

---

## `updateUser()` — Partial State Update

```jsx
const updateUser = (partial) => setUser(prev => ({ ...prev, ...partial }));
```

Used when the user changes their avatar or profile:
```javascript
updateUser({ avatar_url: '/static/avatars/user_1_abc.jpg' });
// prev = { id:1, username:"vinod", avatar_url: null, role:"admin" }
// next = { id:1, username:"vinod", avatar_url: "/static/avatars/...", role:"admin" }
```

**Functional update pattern:** `setUser(prev => newValue)` — when the new state depends
on the previous state, always use the function form. If you call `setUser({ ...user, ...partial })`,
and React batches multiple state updates, `user` might be stale.

---

## Context Value Provided

```jsx
return (
  <AuthContext.Provider value={{
    user,             // User object or null
    menus,            // Array of menu objects with can_view/insert/update/delete
    loading,          // true during initial token validation
    login,            // async (username, password) → void
    logout,           // () → void
    updateUser,       // (partial: Partial<User>) → void
    isAuthenticated: !!user,  // Computed boolean
  }}>
    {children}
  </AuthContext.Provider>
);
```

`isAuthenticated: !!user` — double negation converts `null` → `false`, object → `true`.
More readable than `user !== null` in JSX conditions.

---

## `services/authService.js`

```javascript
import api from './api';
import { TOKEN_KEY } from '../utils/constants';

export const authService = {
  login: async (username, password) => {
    const params = new URLSearchParams({ username, password });
    const res = await api.post('/auth/token', params);
    localStorage.setItem(TOKEN_KEY, res.data.access_token);
  },
  logout: () => localStorage.removeItem(TOKEN_KEY),
  getMe:  () => api.get('/users/me'),
  isAuthenticated: () => !!localStorage.getItem(TOKEN_KEY),
};
```

### `URLSearchParams` — Why Form Encoding?

The FastAPI login endpoint uses `OAuth2PasswordRequestForm` which expects
`Content-Type: application/x-www-form-urlencoded`, not JSON.

```javascript
// Wrong — sends JSON
api.post('/auth/token', { username, password })
// → Content-Type: application/json
// → FastAPI returns 422 Unprocessable Entity

// Correct — sends form data
const params = new URLSearchParams({ username, password });
api.post('/auth/token', params)
// → Content-Type: application/x-www-form-urlencoded
// → Body: username=vinod&password=mypass
// → FastAPI returns { access_token: "...", token_type: "bearer" }
```

`URLSearchParams` automatically encodes special characters: `p@ss` → `p%40ss`.

### `isAuthenticated: () => !!localStorage.getItem(TOKEN_KEY)`

Returns `true` if a token exists in `localStorage`, `false` otherwise.
This is a **synchronous** check — it does NOT validate the token.
Token validation happens asynchronously via `/users/me` in `AuthContext.useEffect`.

---

## `hooks/useAuth.js` — Re-Export Pattern

```javascript
export { useAuth } from '../context/AuthContext';
```

`useAuth` is defined in `AuthContext.jsx` but re-exported from `hooks/useAuth.js`.
This gives components a consistent import path (`../hooks/useAuth`) regardless of
where the context file lives. If you refactor and move `AuthContext`, only this file changes.

---

## How Any Component Consumes Auth State

```jsx
// In any component, anywhere in the tree:
import { useAuth } from '../hooks/useAuth';

function Header() {
  const { user, logout, isAuthenticated } = useAuth();

  return (
    <header>
      {isAuthenticated && (
        <>
          <span>Welcome, {user.username}</span>
          <button onClick={logout}>Logout</button>
        </>
      )}
    </header>
  );
}
```

No props passed, no prop drilling — the component reaches up into the context tree.

---

## Interview Questions

**Q: What is the Context API and when should you use Redux instead?**

Context API: Built-in React. Good for data that rarely changes and is needed in many
places — auth state, theme, language. Re-renders all consumers when context value changes.

Redux: External library. Good for complex, frequently-changing state with many interactions
(shopping cart, real-time trading data). Uses selectors to prevent unnecessary re-renders.

For auth state (changes once on login/logout), Context is the right choice.

**Q: What is prop drilling and how does Context solve it?**

Prop drilling = passing data through components that don't use it, just to reach a
deep child. `App → Layout → Header → Avatar → { user }`. Header and Avatar must
receive `user` as a prop even if they don't need it.

Context solves this by making `user` available to any component via `useAuth()`,
skipping the entire prop chain.

**Q: Why does React Context cause performance issues and how would you fix them?**

When the context value changes, ALL consumers re-render. If `loading`, `user`, AND `menus`
are in the same context, a menu update re-renders every component using `useAuth()`.

Fix: Split into multiple contexts — `AuthContext` (user, loading) and `MenuContext` (menus).
Components that only need menus won't re-render when user changes.

Alternative: `useMemo` the context value to prevent unnecessary object recreation.
