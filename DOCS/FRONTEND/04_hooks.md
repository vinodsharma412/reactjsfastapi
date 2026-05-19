# Frontend — Custom Hooks (`hooks/`)

## What Are Custom Hooks?

A custom hook is a JavaScript function that starts with `use` and calls other React hooks.
They extract stateful logic from components into reusable functions.

**Rule:** hooks can only be called inside React components or other hooks.
Custom hooks let you share logic without sharing UI.

---

## `hooks/useSSE.js` — Server-Sent Events Stream

```javascript
export default function useSSE(path, init = null) {
  const [data,      setData]      = useState(init);
  const [connected, setConnected] = useState(false);
  const abortRef  = useRef(null);    // AbortController
  const activeRef = useRef(false);   // Is this hook still mounted?

  useEffect(() => {
    if (!path) return;   // Disabled when path is null

    activeRef.current = true;
    abortRef.current  = new AbortController();

    async function connect() {
      const token = localStorage.getItem(TOKEN_KEY);
      const url   = `${API_URL}${path}`;

      try {
        const resp = await fetch(url, {
          headers: { Authorization: token ? `Bearer ${token}` : '' },
          signal:  abortRef.current.signal,
        });

        if (!resp.ok || !resp.body) {
          scheduleReconnect();
          return;
        }

        setConnected(true);
        const reader  = resp.body.getReader();
        const decoder = new TextDecoder();
        let   buf     = '';

        while (activeRef.current) {
          const { done, value } = await reader.read();
          if (done) break;

          buf += decoder.decode(value, { stream: true });
          const frames = buf.split('\n\n');
          buf = frames.pop();   // Keep incomplete trailing frame

          for (const frame of frames) {
            const line = frame.split('\n').find(l => l.startsWith('data: '));
            if (line) {
              try { setData(JSON.parse(line.slice(6))); } catch { }
            }
          }
        }
      } catch (err) {
        if (!activeRef.current) return;   // Unmounted — don't reconnect
        scheduleReconnect();
      } finally {
        setConnected(false);
      }
    }

    function scheduleReconnect() {
      if (activeRef.current) setTimeout(connect, 3000);
    }

    connect();

    return () => {
      activeRef.current = false;
      abortRef.current?.abort();   // Cancel the fetch on unmount
    };
  }, [path]);

  return { data, connected };
}
```

### `useRef` for `activeRef` and `abortRef`

**Why `useRef` and not `useState`?**

`useRef` returns the same object across renders. Changing `.current` does NOT trigger a re-render.

If `activeRef` was a state variable:
```javascript
const [active, setActive] = useState(true);
// In cleanup: setActive(false)
// → triggers re-render → runs useEffect cleanup again → sets active to false → infinite loop
```

`useRef` is the correct tool for values that:
1. Need to persist across renders (same as state)
2. Should NOT trigger re-renders when changed (unlike state)
3. Need to be read inside async callbacks (closures capture `.current`, not the value)

### The SSE Protocol

Server-Sent Events send text frames over a persistent HTTP connection:
```
data: {"pending": 5, "completed": 3}\n\n
data: {"pending": 4, "completed": 4}\n\n
```

Each frame:
- Starts with `data: ` prefix
- Ends with `\n\n` (double newline marks frame boundary)

```javascript
// Parse the stream:
buf += decoder.decode(value, { stream: true });
const frames = buf.split('\n\n');
buf = frames.pop();   // Last item might be incomplete
```

`decode(value, { stream: true })` — `stream: true` tells the decoder "more bytes coming."
This correctly handles multi-byte UTF-8 characters that span chunk boundaries.

`frames.pop()` — The last element after splitting on `\n\n` might be an incomplete frame
(e.g., half of the next JSON). We keep it in `buf` and append future bytes to it.

### Auto-Reconnect

```javascript
function scheduleReconnect() {
  if (activeRef.current) setTimeout(connect, 3000);
}
```

If the connection drops (network blip, server restart), reconnect after 3 seconds.
`activeRef.current` check prevents reconnecting after the component unmounts.

### Cleanup on Unmount

```javascript
return () => {
  activeRef.current = false;
  abortRef.current?.abort();
};
```

`AbortController.abort()` cancels the pending `fetch()` call — the `signal` passed
to `fetch` is signalled, causing the request to reject with `AbortError`.

The `catch` block checks `if (!activeRef.current) return` — doesn't reconnect if unmounted.

### Usage

```jsx
function AmazonScraper({ jobId }) {
  const { data: job, connected } = useSSE(
    jobId ? `/scraping/jobs/${jobId}/stream` : null
  );

  return (
    <div>
      {connected ? '🟢 Live' : '🔴 Disconnected'}
      <p>Completed: {job?.completed}/{job?.total}</p>
    </div>
  );
}
```

---

## `hooks/usePagination.js` — Page State Management

```javascript
export default function usePagination(defaultPageSize = 10) {
  const [page,     setPage]     = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const goTo       = useCallback(p    => setPage(p), []);
  const resetPage  = useCallback(()   => setPage(1), []);
  const changeSize = useCallback(size => { setPageSize(size); setPage(1); }, []);

  const paginate = useCallback((rows) => {
    const total      = rows.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const safePage   = Math.min(page, totalPages);   // Clamp to valid range
    const start      = (safePage - 1) * pageSize;
    return {
      pageRows:    rows.slice(start, start + pageSize),
      totalRows:   total,
      totalPages,
      currentPage: safePage,
      start: total === 0 ? 0 : start + 1,    // 1-indexed for display
      end:   Math.min(start + pageSize, total),
    };
  }, [page, pageSize]);

  return { page, pageSize, goTo, resetPage, changeSize, paginate };
}
```

### Why `Math.min(page, totalPages)` — Safe Page?

When a filter reduces results from 50 to 3 items, and you're on page 5 (10 per page):
- `totalPages = Math.ceil(3/10) = 1`
- `page = 5` (stale)
- `safePage = Math.min(5, 1) = 1`

Without this: you'd try to show rows `40-50` of a 3-item array → empty page.
`safePage` clamps to valid range without resetting the state.

### `changeSize` Resets to Page 1

```javascript
const changeSize = useCallback(size => {
  setPageSize(size);
  setPage(1);   // ← Reset page when page size changes
}, []);
```

If you're on page 5 (10 per page, 50 items) and change to 25 per page:
- Page 5 with 25 per page = items 101-125 (doesn't exist)
- Reset to page 1 = items 1-25 ✅

### Usage

```jsx
function UsersTable({ users }) {
  const { page, pageSize, goTo, changeSize, paginate } = usePagination(10);
  const { pageRows, totalPages, start, end, totalRows } = paginate(users);

  return (
    <>
      <table>
        {pageRows.map(user => <UserRow key={user.id} user={user} />)}
      </table>
      <p>Showing {start}-{end} of {totalRows}</p>
      <Pagination current={page} total={totalPages} onChange={goTo} />
    </>
  );
}
```

---

## `hooks/useSortFilter.js` — Sort + Search + Filter

```javascript
export function useSortFilter(defaultSortCol = '') {
  const [search,       setSearch]       = useState('');
  const [sortBy,       setSortBy]       = useState({ col: defaultSortCol, dir: 'asc' });
  const [filterValues, setFilterValues] = useState({});

  const handleSort = useCallback(col => {
    setSortBy(prev => ({
      col,
      dir: prev.col === col && prev.dir === 'asc' ? 'desc' : 'asc',
    }));
  }, []);
```

**Toggle sort direction:**
- Click column "username" first time → `{ col: 'username', dir: 'asc' }`
- Click "username" again → `{ col: 'username', dir: 'desc' }`
- Click different column "email" → `{ col: 'email', dir: 'asc' }` (resets to asc)

```javascript
export function applySort(rows, sortBy) {
  if (!sortBy.col) return rows;
  return [...rows].sort((a, b) => {
    const va = a[sortBy.col] ?? '';
    const vb = b[sortBy.col] ?? '';
    let cmp;
    if (typeof va === 'boolean')     cmp = va === vb ? 0 : va ? -1 : 1;
    else if (typeof va === 'number') cmp = va - vb;
    else cmp = String(va).localeCompare(String(vb), undefined, {
      numeric: true,      // "10" sorts after "9" (not before as in ASCII)
      sensitivity: 'base' // Case-insensitive
    });
    return sortBy.dir === 'asc' ? cmp : -cmp;
  });
}
```

**`String.localeCompare` with `numeric: true`:**

Without `numeric`: `["2", "10", "1"].sort()` → `["1", "10", "2"]` (ASCII order).
With `numeric: true`: `["2", "10", "1"].sort(localeCompare)` → `["1", "2", "10"]` (natural order).

**`[...rows].sort()`:** Creates a new array before sorting. `Array.sort()` mutates in place.
If `rows` came from state, mutating it would modify state without `setState` — a React anti-pattern.

```javascript
export function applySearch(rows, search, fields) {
  if (!search.trim()) return rows;
  const q = search.toLowerCase();
  return rows.filter(row =>
    fields.some(f => String(row[f] ?? '').toLowerCase().includes(q))
  );
}
```

`fields.some()` — returns `true` if any field matches. Searching across multiple columns.
`?? ''` — nullish coalescing: if `row[f]` is `null` or `undefined`, use `''`. Prevents `String(null)` → `"null"`.

---

## `hooks/useMenuAccess.js` — Per-Page CRUD Permissions

```javascript
export function useMenuAccess(path) {
  const { menus } = useAuth();
  const menu = menus?.find(m => m.path === path);
  return {
    canView:   menu?.can_view   ?? false,
    canInsert: menu?.can_insert ?? false,
    canUpdate: menu?.can_update ?? false,
    canDelete: menu?.can_delete ?? false,
  };
}
```

**Usage in a component:**

```jsx
function UsersPage() {
  const { canInsert, canUpdate, canDelete } = useMenuAccess('/users');

  return (
    <div>
      {canInsert && <button onClick={openCreateModal}>Add User</button>}
      <table>
        {users.map(user => (
          <tr key={user.id}>
            <td>{user.username}</td>
            {canUpdate && <td><button>Edit</button></td>}
            {canDelete && <td><button>Delete</button></td>}
          </tr>
        ))}
      </table>
    </div>
  );
}
```

The `Add User` button, Edit and Delete columns only render if the current user's
menu permissions allow them. This is **frontend enforcement** — backend also validates
via `require_roles()`. Frontend hides the button; backend rejects unauthorised requests.

---

## `hooks/useConfirm.js` — Reusable Confirmation Dialog

```javascript
export default function useConfirm() {
  const [state, setState] = useState({ open: false, message: '', resolve: null });

  const confirm = useCallback((message) => {
    return new Promise((resolve) => {
      setState({ open: true, message, resolve });
    });
  }, []);

  const handleYes = () => {
    state.resolve(true);
    setState({ open: false, message: '', resolve: null });
  };

  const handleNo = () => {
    state.resolve(false);
    setState({ open: false, message: '', resolve: null });
  };

  return { confirm, isOpen: state.open, message: state.message, handleYes, handleNo };
}
```

**Pattern: Promise-based UI interaction**

```jsx
const { confirm, ...dialogProps } = useConfirm();

const handleDelete = async (userId) => {
  const yes = await confirm('Are you sure you want to delete this user?');
  if (yes) {
    await userService.remove(userId);
  }
};
```

`confirm()` returns a Promise that resolves when the user clicks Yes or No.
This turns an asynchronous UI interaction (user clicking a button) into awaitable code.

The component renders the dialog using `dialogProps`:
```jsx
<ConfirmDialog
  open={dialogProps.isOpen}
  message={dialogProps.message}
  onConfirm={dialogProps.handleYes}
  onCancel={dialogProps.handleNo}
/>
```

---

## Why `useCallback` on All Hook Functions?

```javascript
const goTo = useCallback(p => setPage(p), []);
```

When a hook returns a function, it's often passed as a prop or used in `useEffect`.
Without `useCallback`, a new function object is created on every render.
New reference → prop changed → child re-renders unnecessarily.
With `useCallback([])` — same function reference on every render — stable identity.

---

## Interview Questions

**Q: What is the difference between `useRef` and `useState`?**

Both persist values across renders. The difference:
- `useState`: changing value triggers a re-render
- `useRef`: changing `.current` does NOT trigger a re-render

Use `useState` for values that drive UI. Use `useRef` for:
- DOM element references (`ref={myRef}`)
- Values needed in async callbacks (event handlers, setTimeout, fetch)
- Mutable values that don't affect rendering

**Q: How does `useCallback` prevent unnecessary re-renders?**

React uses **referential equality** (`===`) to compare props. Two functions with the
same body are NOT equal: `() => x === () => x` is `false`.
Without `useCallback`, every render creates a new function → child's prop changed → child re-renders.
With `useCallback(fn, [deps])`, the same function reference is returned on each render
unless `deps` changed — preventing unnecessary child re-renders.

**Q: What is `React.memo` and how does it work with `useCallback`?**

`React.memo(Component)` prevents a component from re-rendering unless its props change.
But if the parent passes a new function on every render, `memo` is useless (props changed = new function).
`useCallback` + `React.memo` work together: `useCallback` ensures stable function references,
`memo` ensures the child only re-renders when those references actually change.
