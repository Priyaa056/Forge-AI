"""UI Agent code writer: React 18 + Vite single-page application driven by ui_spec.json."""

import json
from typing import Dict, List

from backend.codegen.blueprint import Blueprint, entity_ui_config
from backend.codegen.naming import to_pascal
from backend.codegen.project_files import GeneratedProject

AGENT = "ui"

FRONTEND_DEPENDENCIES = {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2",
}
FRONTEND_DEV_DEPENDENCIES = {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.8",
}

THEMES = {
    "task_management": "#4f46e5", "project_management": "#4f46e5", "ecommerce": "#ea580c", "blog": "#0284c7",
    "healthcare": "#0d9488", "education": "#7c3aed", "finance": "#16a34a", "crm": "#2563eb", "hr": "#0891b2",
    "inventory": "#ca8a04", "library": "#9333ea", "recipes": "#dc2626", "helpdesk": "#db2777", "events": "#c026d3",
}


def page_component_name(entity_plural_label: str) -> str:
    return f"{to_pascal(entity_plural_label)}Page"


def build_ui_spec(bp: Blueprint, styling: Dict = None) -> Dict:
    """UIOutput-compatible specification (pages, components, routes, forms, API requirements, styling)."""
    styling = styling or {}
    primary = styling.get("primary_color") or THEMES.get(bp.app_type, "#2563eb")
    pages, routes, forms, api = [], [], [], []

    pages.append({"name": "LoginPage", "route_path": "/login", "layout": "AuthLayout", "description": "Sign in with email and password",
                  "components_used": ["AuthCard"], "required_auth": False, "state_requirements": ["email", "password", "error"]})
    pages.append({"name": "RegisterPage", "route_path": "/register", "layout": "AuthLayout", "description": "Create an account",
                  "components_used": ["AuthCard"], "required_auth": False, "state_requirements": ["full_name", "email", "password"]})
    pages.append({"name": "DashboardPage", "route_path": "/", "layout": "MainLayout",
                  "description": f"Overview of the signed-in user's {', '.join(e.plural_label.lower() for e in bp.entities)}",
                  "components_used": ["Layout", "StatCard"], "required_auth": True, "state_requirements": ["summary"]})
    for e in bp.entities:
        pages.append({"name": page_component_name(e.plural_label), "route_path": e.ui_path, "layout": "MainLayout",
                      "description": f"Search, filter, create, edit and delete {e.plural_label.lower()}",
                      "components_used": ["Layout", "ResourcePage", "EntityForm", "Modal"], "required_auth": True,
                      "state_requirements": ["items", "total", "query", "filters", "editing"]})
        forms.append({"name": f"{e.name}Form", "form_name": f"{e.name}Form", "entity_name": e.name,
                      "fields": [{"name": f.name, "label": f.label, "input_type": f.input_type, "required": f.required,
                                  **({"options": f.enum_values} if f.enum_values else {}),
                                  **({"references": f.references} if f.references else {})}
                                 for f in e.editable_fields],
                      "submit_endpoint": e.api_path,
                      "validation_rules": [f"{f.name} is required" for f in e.editable_fields if f.required]})
        api += [
            {"endpoint": e.api_path, "method": "GET", "description": f"Load {e.plural_label.lower()}"},
            {"endpoint": e.api_path, "method": "POST", "description": f"Create {e.label.lower()}"},
            {"endpoint": f"{e.api_path}/{{id}}", "method": "PUT", "description": f"Update {e.label.lower()}"},
            {"endpoint": f"{e.api_path}/{{id}}", "method": "DELETE", "description": f"Delete {e.label.lower()}"},
        ]
    if bp.has_admin_dashboard:
        pages.append({"name": "AdminPage", "route_path": "/admin", "layout": "MainLayout",
                      "description": "Statistics, status breakdowns and user management (admins only)",
                      "components_used": ["Layout", "StatCard", "BarList", "UsersTable"], "required_auth": True,
                      "state_requirements": ["stats", "users"]})
        api += [
            {"endpoint": "/api/admin/stats", "method": "GET", "description": "Admin statistics"},
            {"endpoint": "/api/users", "method": "GET", "description": "List users"},
            {"endpoint": "/api/users/{id}", "method": "PUT", "description": "Change role / active flag"},
            {"endpoint": "/api/users/{id}", "method": "DELETE", "description": "Delete user"},
        ]
    api += [
        {"endpoint": "/api/auth/login", "method": "POST", "description": "Sign in"},
        {"endpoint": "/api/auth/register", "method": "POST", "description": "Register"},
        {"endpoint": "/api/auth/me", "method": "GET", "description": "Current user"},
        {"endpoint": "/api/dashboard/summary", "method": "GET", "description": "Dashboard counts"},
    ]
    for p in pages:
        routes.append({"path": p["route_path"], "component_name": p["name"], "exact": True,
                       "protected": p["required_auth"], "title": p["description"][:60]})
    components = [
        {"name": "Layout", "type": "layout", "description": "Sidebar navigation, header with user menu and logout",
         "props": [{"name": "children", "type": "node"}], "state_variables": [{"name": "menuOpen", "default": "false"}],
         "event_handlers": ["logout"], "child_components": []},
        {"name": "ResourcePage", "type": "container", "description": "Data table with search, filters, pagination and CRUD modal",
         "props": [{"name": "config", "type": "object"}], "state_variables": [{"name": "items", "default": "[]"}],
         "event_handlers": ["onSearch", "onFilter", "onCreate", "onEdit", "onDelete"], "child_components": ["EntityForm", "Modal"]},
        {"name": "EntityForm", "type": "form", "description": "Typed form generated from field metadata with client-side validation",
         "props": [{"name": "config", "type": "object"}, {"name": "initial", "type": "object"}],
         "state_variables": [{"name": "values", "default": "{}"}], "event_handlers": ["onSubmit"], "child_components": []},
        {"name": "Modal", "type": "presentational", "description": "Accessible dialog", "props": [{"name": "title", "type": "string"}],
         "state_variables": [], "event_handlers": ["onClose"], "child_components": []},
        {"name": "StatCard", "type": "presentational", "description": "Metric card", "props": [{"name": "label", "type": "string"}],
         "state_variables": [], "event_handlers": [], "child_components": []},
    ]
    return {
        "project_name": bp.project_name,
        "pages": pages,
        "components": components,
        "routes": routes,
        "layouts": [
            {"name": "MainLayout", "description": "Authenticated shell with sidebar", "slots": ["main"], "default_layout": True},
            {"name": "AuthLayout", "description": "Centered card for sign-in/registration", "slots": ["main"], "default_layout": False},
        ],
        "forms": forms,
        "frontend_dependencies": [
            {"package_name": k, "version": v, "purpose": "UI runtime", "category": "core"} for k, v in FRONTEND_DEPENDENCIES.items()
        ] + [
            {"package_name": k, "version": v, "purpose": "Build tooling", "category": "dev"} for k, v in FRONTEND_DEV_DEPENDENCIES.items()
        ],
        "api_requirements": api,
        "styling_requirements": {
            "theme_mode": "light",
            "primary_color": primary,
            "font_family": "Inter, system-ui, sans-serif",
            "design_system_notes": styling.get("design_system_notes") or "Clean dashboard layout with sidebar navigation, cards and data tables",
            "css_approach": "Vanilla CSS with custom properties",
        },
    }


# ---------------------------------------------------------------------------------------------
# Static source files
# ---------------------------------------------------------------------------------------------

API_CLIENT_JS = """// API client (generated by FORGE AI UI Agent). Adds the JWT and turns API errors into readable messages.
const TOKEN_KEY = '__TOKEN_KEY__';
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

let token = null;
try { token = window.localStorage.getItem(TOKEN_KEY); } catch { token = null; }

export function getAuthToken() { return token; }

export function setAuthToken(value) {
  token = value || null;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable */ }
}

function formatError(data, status) {
  const detail = data && data.detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(-1)[0] || 'field'}: ${d.msg}`).join('; ');
  }
  if (typeof detail === 'string') return detail;
  return `Request failed (${status})`;
}

async function request(method, path, { body, params } = {}) {
  const url = new URL(BASE_URL + path, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  });
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (response.status === 401 && token && !path.startsWith('/api/auth/')) setAuthToken(null);
  if (!response.ok) throw new Error(formatError(data, response.status));
  return data;
}

export const api = {
  get: (path, params) => request('GET', path, { params }),
  post: (path, body) => request('POST', path, { body }),
  put: (path, body) => request('PUT', path, { body }),
  delete: (path) => request('DELETE', path),
};
"""

MAIN_JSX = """import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './auth/AuthContext.jsx';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
"""

LAYOUT_JSX = """import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.jsx';
import { APP_NAME, NAV_ITEMS } from '../config/app.js';

export default function Layout({ children }) {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const items = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  const handleLogout = () => { logout(); navigate('/login'); };

  return (
    <div className="shell">
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="brand">{APP_NAME}</div>
        <nav>
          {items.map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === '/'} onClick={() => setMenuOpen(false)}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost menu-toggle" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle menu">☰</button>
          <div className="spacer" />
          <div className="user-chip">
            <span className="avatar">{(user?.full_name || '?').slice(0, 1).toUpperCase()}</span>
            <span><strong>{user?.full_name}</strong><small>{user?.role}</small></span>
          </div>
          <button className="btn btn-ghost" onClick={handleLogout}>Log out</button>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
"""

MODAL_JSX = """export default function Modal({ title, onClose, children }) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
"""

FORMAT_JS = """// Value formatting helpers shared by tables and forms.
export function humanize(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

export function formatValue(field, value, refLabels = {}) {
  if (value === null || value === undefined || value === '') return '—';
  switch (field.kind) {
    case 'boolean': return value ? 'Yes' : 'No';
    case 'enum': return humanize(value);
    case 'reference': return refLabels[field.name]?.[value] ?? `#${value}`;
    case 'decimal': return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    case 'datetime': return new Date(value).toLocaleString();
    case 'date': return new Date(`${value}T00:00:00`).toLocaleDateString();
    case 'text': return String(value).length > 60 ? `${String(value).slice(0, 60)}…` : String(value);
    default: return String(value);
  }
}

export function toInputValue(field, value) {
  if (value === null || value === undefined) return field.type === 'checkbox' ? false : '';
  if (field.kind === 'datetime') return String(value).slice(0, 16);
  return value;
}

export function fromInputValue(field, value) {
  if (field.type === 'checkbox') return Boolean(value);
  if (value === '' || value === null || value === undefined) return null;
  if (field.kind === 'integer' || field.kind === 'reference') return parseInt(value, 10);
  if (field.kind === 'float' || field.kind === 'decimal') return parseFloat(value);
  if (field.kind === 'datetime') return new Date(value).toISOString();
  return value;
}
"""

ENTITY_FORM_JSX = """import { useState } from 'react';
import { fromInputValue, toInputValue } from '../utils/format.js';

export default function EntityForm({ config, initial, refOptions, onSubmit, onCancel }) {
  const editable = config.fields.filter((f) => !f.readOnly);
  const [values, setValues] = useState(() => Object.fromEntries(editable.map((f) => {
    const start = initial ? initial[f.name] : (f.default !== undefined ? (f.type === 'checkbox' ? f.default === 'true' : f.default) : null);
    return [f.name, toInputValue(f, start)];
  })));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const set = (name, value) => setValues((v) => ({ ...v, [name]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    const payload = {};
    for (const f of editable) {
      const value = fromInputValue(f, values[f.name]);
      if (f.required && (value === null || value === '')) { setError(`${f.label} is required`); return; }
      if (value !== null || initial) payload[f.name] = value;
    }
    setBusy(true);
    try {
      await onSubmit(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const renderInput = (f) => {
    const common = { id: `field-${f.name}`, name: f.name, required: f.required };
    if (f.type === 'textarea') return <textarea {...common} rows={4} value={values[f.name]} onChange={(e) => set(f.name, e.target.value)} />;
    if (f.type === 'checkbox') return <input {...common} required={false} type="checkbox" checked={Boolean(values[f.name])} onChange={(e) => set(f.name, e.target.checked)} />;
    if (f.type === 'select') {
      return (
        <select {...common} value={values[f.name] ?? ''} onChange={(e) => set(f.name, e.target.value)}>
          {!f.required && <option value="">—</option>}
          {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    }
    if (f.type === 'reference') {
      const options = refOptions[f.name] || [];
      return (
        <select {...common} value={values[f.name] ?? ''} onChange={(e) => set(f.name, e.target.value)}>
          <option value="">{f.required ? `Select ${f.label.toLowerCase()}…` : '—'}</option>
          {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
      );
    }
    return (
      <input {...common} type={f.type} min={f.min} max={f.max} step={f.step || (f.type === 'number' ? '1' : undefined)}
        value={values[f.name] ?? ''} onChange={(e) => set(f.name, e.target.value)} />
    );
  };

  return (
    <form className="entity-form" onSubmit={submit}>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      <div className="form-grid">
        {editable.map((f) => (
          <label key={f.name} htmlFor={`field-${f.name}`} className={f.type === 'textarea' ? 'span-2' : f.type === 'checkbox' ? 'checkbox-row' : ''}>
            <span>{f.label}{f.required && <em className="req">*</em>}</span>
            {renderInput(f)}
          </label>
        ))}
      </div>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      </div>
    </form>
  );
}
"""

RESOURCE_PAGE_JSX = """import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import EntityForm from './EntityForm.jsx';
import Modal from './Modal.jsx';
import { formatValue, humanize } from '../utils/format.js';

const PAGE_SIZE = 10;

export default function ResourcePage({ config }) {
  const { isAdmin } = useAuth();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState(null);
  const [refOptions, setRefOptions] = useState({});

  const canWrite = config.access !== 'admin_managed' || isAdmin;
  const canDelete = canWrite && (config.access !== 'shared' || isAdmin);
  const columns = useMemo(() => config.fields.filter((f) => f.name !== 'owner_id' && f.kind !== 'text').slice(0, 7), [config]);
  const filterFields = useMemo(() => config.fields.filter((f) => config.filters.includes(f.name)), [config]);

  const refLabels = useMemo(() => Object.fromEntries(Object.entries(refOptions).map(
    ([field, options]) => [field, Object.fromEntries(options.map((o) => [o.id, o.label]))])), [refOptions]);

  useEffect(() => {
    config.fields.filter((f) => f.kind === 'reference' && f.reference?.endpoint).forEach((f) => {
      api.get(f.reference.endpoint, { limit: 200 })
        .then((data) => setRefOptions((prev) => ({ ...prev, [f.name]: data.items.map((r) => ({ id: r.id, label: String(r[f.reference.labelField] ?? `#${r.id}`) })) })))
        .catch(() => {});
    });
  }, [config]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.get(config.endpoint, { q: search, skip: page * PAGE_SIZE, limit: PAGE_SIZE, ...filters });
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [config.endpoint, search, page, filters]);

  useEffect(() => { load(); }, [load]);

  const save = async (payload) => {
    if (editing && editing.id) {
      await api.put(`${config.endpoint}/${editing.id}`, payload);
      setNotice(`${config.label} updated`);
    } else {
      await api.post(config.endpoint, payload);
      setNotice(`${config.label} created`);
    }
    setEditing(null);
    load();
  };

  const remove = async (item) => {
    if (!window.confirm(`Delete this ${config.label.toLowerCase()}?`)) return;
    try {
      await api.delete(`${config.endpoint}/${item.id}`);
      setNotice(`${config.label} deleted`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>{config.pluralLabel}</h1>
          <p className="muted">{total} record{total === 1 ? '' : 's'}{config.access === 'owner' && !isAdmin ? ' (yours)' : ''}</p>
        </div>
        {canWrite && <button className="btn btn-primary" onClick={() => setEditing({})}>+ New {config.label.toLowerCase()}</button>}
      </div>

      <div className="toolbar card">
        {config.searchable && (
          <form className="search" onSubmit={(e) => { e.preventDefault(); setPage(0); setSearch(query); }}>
            <input type="search" placeholder={`Search ${config.pluralLabel.toLowerCase()}…`} value={query} onChange={(e) => setQuery(e.target.value)} />
            <button className="btn" type="submit">Search</button>
          </form>
        )}
        {filterFields.map((f) => (
          <select key={f.name} aria-label={`Filter by ${f.label}`} value={filters[f.name] ?? ''}
            onChange={(e) => { setPage(0); setFilters({ ...filters, [f.name]: e.target.value }); }}>
            <option value="">All {f.label.toLowerCase()}</option>
            {f.kind === 'boolean' && [<option key="t" value="true">Yes</option>, <option key="f" value="false">No</option>]}
            {f.options && f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            {f.kind === 'reference' && (refOptions[f.name] || []).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        ))}
      </div>

      {notice && <div className="alert alert-success" onAnimationEnd={() => setNotice('')}>{notice}</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      <div className="card table-card">
        {loading ? <div className="empty-state">Loading…</div> : items.length === 0 ? (
          <div className="empty-state">
            <h3>No {config.pluralLabel.toLowerCase()} yet</h3>
            {canWrite && <p>Create the first one with “New {config.label.toLowerCase()}”.</p>}
          </div>
        ) : (
          <table>
            <thead><tr>{columns.map((c) => <th key={c.name}>{c.label}</th>)}<th aria-label="Actions" /></tr></thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  {columns.map((c) => (
                    <td key={c.name} data-label={c.label}>
                      {c.kind === 'enum' ? <span className={`badge badge-${item[c.name]}`}>{humanize(item[c.name])}</span> : formatValue(c, item[c.name], refLabels)}
                    </td>
                  ))}
                  <td className="row-actions">
                    {canWrite && <button className="btn btn-small" onClick={() => setEditing(item)}>Edit</button>}
                    {canDelete && <button className="btn btn-small btn-danger" onClick={() => remove(item)}>Delete</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {pages > 1 && (
        <div className="pagination">
          <button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page + 1} of {pages}</span>
          <button className="btn" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}

      {editing && (
        <Modal title={editing.id ? `Edit ${config.label.toLowerCase()}` : `New ${config.label.toLowerCase()}`} onClose={() => setEditing(null)}>
          <EntityForm config={config} initial={editing.id ? editing : null} refOptions={refOptions}
            onSubmit={save} onCancel={() => setEditing(null)} />
        </Modal>
      )}
    </section>
  );
}
"""

DASHBOARD_JSX = """import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { APP_DESCRIPTION, FEATURES } from '../config/app.js';

export default function DashboardPage() {
  const { user, isAdmin } = useAuth();
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { api.get('/api/dashboard/summary').then(setSummary).catch((e) => setError(e.message)); }, []);

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>Welcome, {user?.full_name?.split(' ')[0]}</h1>
          <p className="muted">{APP_DESCRIPTION}</p>
        </div>
        {isAdmin && <Link className="btn btn-primary" to="/admin">Admin dashboard</Link>}
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <div className="stat-grid">
        {(summary?.entities || []).map((e) => (
          <Link key={e.name} to={e.path} className="card stat-card">
            <span className="stat-label">{e.label}</span>
            <span className="stat-value">{e.count}</span>
            <span className="stat-link">Open →</span>
          </Link>
        ))}
      </div>
      <div className="card">
        <h2>What you can do</h2>
        <ul className="feature-list">{FEATURES.map((f) => <li key={f}>{f}</li>)}</ul>
      </div>
    </section>
  );
}
"""

ADMIN_JSX = """import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { ROLES } from '../config/app.js';
import { humanize } from '../utils/format.js';

export default function AdminPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api.get('/api/admin/stats').then(setStats).catch((e) => setError(e.message));
    api.get('/api/users', { limit: 200 }).then((d) => setUsers(d.items)).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { load(); }, [load]);

  const updateUser = async (target, changes) => {
    try { await api.put(`/api/users/${target.id}`, changes); load(); } catch (e) { setError(e.message); }
  };
  const deleteUser = async (target) => {
    if (!window.confirm(`Delete ${target.email}? Their records are deleted too.`)) return;
    try { await api.delete(`/api/users/${target.id}`); load(); } catch (e) { setError(e.message); }
  };

  return (
    <section>
      <div className="page-header"><div><h1>Admin dashboard</h1><p className="muted">System-wide statistics and user management</p></div></div>
      {error && <div className="alert alert-error">{error}</div>}
      <div className="stat-grid">
        <div className="card stat-card"><span className="stat-label">Users</span><span className="stat-value">{stats?.totals?.users ?? '…'}</span></div>
        {(stats?.entities || []).map((e) => (
          <div key={e.name} className="card stat-card"><span className="stat-label">{e.label}</span><span className="stat-value">{e.count}</span></div>
        ))}
      </div>
      <div className="two-col">
        {(stats?.breakdowns || []).map((b) => {
          const max = Math.max(1, ...Object.values(b.counts));
          return (
            <div key={`${b.entity}-${b.field}`} className="card">
              <h2>{b.entity} by {b.field.toLowerCase()}</h2>
              {Object.keys(b.counts).length === 0 ? <p className="muted">No data yet</p> : Object.entries(b.counts).map(([k, v]) => (
                <div key={k} className="bar-row">
                  <span>{humanize(k)}</span>
                  <div className="bar"><div className="bar-fill" style={{ width: `${(v / max) * 100}%` }} /></div>
                  <strong>{v}</strong>
                </div>
              ))}
            </div>
          );
        })}
        <div className="card">
          <h2>Recent {stats?.recent?.entity?.toLowerCase()}</h2>
          {(stats?.recent?.items || []).length === 0 ? <p className="muted">No records yet</p> : (
            <ul className="recent-list">{stats.recent.items.map((r) => (
              <li key={r.id}><span>{r.label}</span><small>{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</small></li>
            ))}</ul>
          )}
        </div>
      </div>
      <div className="card table-card">
        <h2>Users</h2>
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Active</th><th aria-label="Actions" /></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td data-label="Name">{u.full_name}</td>
                <td data-label="Email">{u.email}</td>
                <td data-label="Role">
                  <select value={u.role} disabled={u.id === user.id} onChange={(e) => updateUser(u, { role: e.target.value })}>
                    {ROLES.map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
                  </select>
                </td>
                <td data-label="Active">
                  <input type="checkbox" checked={u.is_active} disabled={u.id === user.id} onChange={(e) => updateUser(u, { is_active: e.target.checked })} />
                </td>
                <td className="row-actions">{u.id !== user.id && <button className="btn btn-small btn-danger" onClick={() => deleteUser(u)}>Delete</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
"""

NOT_FOUND_JSX = """import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="card empty-state">
      <h2>Page not found</h2>
      <p><Link to="/">Back to the dashboard</Link></p>
    </div>
  );
}
"""

STYLES_CSS = """:root {
  --primary: __PRIMARY__;
  --primary-soft: color-mix(in srgb, var(--primary) 12%, white);
  --bg: #f5f6fa;
  --surface: #ffffff;
  --text: #1f2430;
  --muted: #6b7280;
  --border: #e5e7eb;
  --danger: #dc2626;
  --success: #16a34a;
  --radius: 12px;
  font-family: Inter, system-ui, -apple-system, 'Segoe UI', sans-serif;
  color: var(--text);
  background: var(--bg);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); }
a { color: var(--primary); text-decoration: none; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
h2 { font-size: 1.1rem; margin: 0 0 .75rem; }
.muted { color: var(--muted); margin: 0; }
.shell { display: flex; min-height: 100vh; }
.sidebar { width: 240px; background: #111827; color: #e5e7eb; padding: 1.25rem 1rem; flex-shrink: 0; }
.brand { font-weight: 700; font-size: 1.15rem; margin-bottom: 1.5rem; color: white; }
.sidebar nav { display: flex; flex-direction: column; gap: .25rem; }
.nav-link { color: #cbd5e1; padding: .6rem .75rem; border-radius: 8px; }
.nav-link:hover { background: #1f2937; }
.nav-link.active { background: var(--primary); color: white; }
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.topbar { display: flex; align-items: center; gap: .75rem; padding: .75rem 1.5rem; background: var(--surface); border-bottom: 1px solid var(--border); }
.spacer { flex: 1; }
.menu-toggle { display: none; }
.user-chip { display: flex; align-items: center; gap: .5rem; }
.user-chip small { display: block; color: var(--muted); text-transform: capitalize; }
.avatar { width: 34px; height: 34px; border-radius: 50%; background: var(--primary); color: white; display: grid; place-items: center; font-weight: 700; }
.content { padding: 1.5rem; max-width: 1200px; width: 100%; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.25rem; margin-bottom: 1rem; }
.btn { border: 1px solid var(--border); background: var(--surface); color: var(--text); padding: .55rem 1rem; border-radius: 8px; cursor: pointer; font: inherit; }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.btn-primary { background: var(--primary); border-color: var(--primary); color: white; }
.btn-danger { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 35%, white); }
.btn-ghost { background: transparent; border-color: transparent; }
.btn-small { padding: .3rem .6rem; font-size: .85rem; }
.toolbar { display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; padding: .9rem; }
.search { display: flex; gap: .5rem; flex: 1; min-width: 220px; }
input, select, textarea { font: inherit; padding: .55rem .7rem; border: 1px solid var(--border); border-radius: 8px; background: white; width: 100%; }
.toolbar select { width: auto; }
input:focus, select:focus, textarea:focus { outline: 2px solid var(--primary-soft); border-color: var(--primary); }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: .7rem .6rem; border-bottom: 1px solid var(--border); font-size: .92rem; }
th { color: var(--muted); font-weight: 600; font-size: .8rem; text-transform: uppercase; letter-spacing: .03em; }
.table-card { padding: .5rem 1rem; overflow-x: auto; }
.row-actions { display: flex; gap: .4rem; justify-content: flex-end; }
.badge { display: inline-block; padding: .15rem .55rem; border-radius: 999px; background: var(--primary-soft); color: var(--primary); font-size: .8rem; font-weight: 600; }
.badge-done, .badge-completed, .badge-delivered, .badge-paid, .badge-approved, .badge-published, .badge-active, .badge-resolved { background: #dcfce7; color: #166534; }
.badge-cancelled, .badge-rejected, .badge-failed, .badge-overdue, .badge-high, .badge-urgent, .badge-critical { background: #fee2e2; color: #991b1b; }
.alert { padding: .7rem 1rem; border-radius: 8px; margin-bottom: 1rem; }
.alert-error { background: #fee2e2; color: #991b1b; }
.alert-success { background: #dcfce7; color: #166534; animation: fade 3s forwards; }
@keyframes fade { 0%, 80% { opacity: 1; } 100% { opacity: 0; } }
.empty-state { text-align: center; padding: 2.5rem 1rem; color: var(--muted); }
.pagination { display: flex; gap: 1rem; align-items: center; justify-content: center; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1rem; }
.stat-card { display: flex; flex-direction: column; gap: .35rem; margin: 0; color: var(--text); }
.stat-label { color: var(--muted); font-size: .85rem; }
.stat-value { font-size: 2rem; font-weight: 700; }
.stat-link { font-size: .85rem; color: var(--primary); }
.feature-list { margin: 0; padding-left: 1.2rem; line-height: 1.8; }
.two-col { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; }
.bar-row { display: grid; grid-template-columns: 110px 1fr 40px; align-items: center; gap: .6rem; margin: .45rem 0; font-size: .9rem; }
.bar { background: var(--bg); border-radius: 999px; height: 10px; overflow: hidden; }
.bar-fill { background: var(--primary); height: 100%; }
.recent-list { list-style: none; padding: 0; margin: 0; }
.recent-list li { display: flex; justify-content: space-between; padding: .45rem 0; border-bottom: 1px solid var(--border); }
.modal-backdrop { position: fixed; inset: 0; background: rgba(15, 23, 42, .45); display: grid; place-items: center; padding: 1rem; z-index: 50; }
.modal { background: var(--surface); border-radius: var(--radius); width: min(640px, 100%); max-height: 90vh; overflow: auto; padding: 1.25rem; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: .75rem; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .9rem; }
.form-grid label { display: flex; flex-direction: column; gap: .35rem; font-size: .9rem; font-weight: 500; }
.form-grid .span-2 { grid-column: span 2; }
.checkbox-row { flex-direction: row !important; align-items: center; }
.checkbox-row input { width: auto; }
.req { color: var(--danger); font-style: normal; margin-left: .15rem; }
.form-actions { display: flex; justify-content: flex-end; gap: .5rem; margin-top: 1rem; }
.auth-page { min-height: 100vh; display: grid; place-items: center; padding: 1rem; background: linear-gradient(135deg, var(--primary-soft), var(--bg)); }
.auth-card { background: var(--surface); padding: 2rem; border-radius: 16px; width: min(400px, 100%); display: flex; flex-direction: column; gap: .9rem; box-shadow: 0 20px 45px rgba(15, 23, 42, .08); }
.auth-card label { display: flex; flex-direction: column; gap: .35rem; font-size: .9rem; }
.page-loading { padding: 3rem; text-align: center; color: var(--muted); }
@media (max-width: 800px) {
  .sidebar { position: fixed; inset: 0 auto 0 0; transform: translateX(-100%); transition: transform .2s; z-index: 40; }
  .sidebar.open { transform: none; }
  .menu-toggle { display: inline-block; }
  .content { padding: 1rem; }
  .form-grid { grid-template-columns: 1fr; }
  .form-grid .span-2 { grid-column: auto; }
  thead { display: none; }
  tr { display: block; border-bottom: 1px solid var(--border); padding: .5rem 0; }
  td { display: flex; justify-content: space-between; border: none; padding: .3rem 0; }
  td::before { content: attr(data-label); color: var(--muted); font-size: .8rem; }
}
"""


def render_app_jsx(bp: Blueprint) -> str:
    imports = [
        "import { Route, Routes } from 'react-router-dom';",
        "import Layout from './components/Layout.jsx';",
        "import ProtectedRoute from './auth/ProtectedRoute.jsx';",
        "import LoginPage from './pages/LoginPage.jsx';",
        "import RegisterPage from './pages/RegisterPage.jsx';",
        "import DashboardPage from './pages/DashboardPage.jsx';",
        "import NotFoundPage from './pages/NotFoundPage.jsx';",
    ]
    if bp.has_admin_dashboard:
        imports.append("import AdminPage from './pages/AdminPage.jsx';")
    routes = ['          <Route index element={<DashboardPage />} />']
    for e in bp.entities:
        comp = page_component_name(e.plural_label)
        imports.append(f"import {comp} from './pages/{comp}.jsx';")
        routes.append(f'          <Route path="{e.ui_path.lstrip("/")}" element={{<{comp} />}} />')
    if bp.has_admin_dashboard:
        routes.append('          <Route path="admin" element={<ProtectedRoute adminOnly><AdminPage /></ProtectedRoute>} />')
    routes.append('          <Route path="*" element={<NotFoundPage />} />')
    return "\n".join(imports) + """

function Shell({ children }) {
  return <ProtectedRoute><Layout>{children}</Layout></ProtectedRoute>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/*" element={
        <Shell>
          <Routes>
""" + "\n".join(routes) + """
          </Routes>
        </Shell>
      } />
    </Routes>
  );
}
"""


def render_entity_page(e) -> str:
    comp = page_component_name(e.plural_label)
    return f"""import ResourcePage from '../components/ResourcePage.jsx';
import {{ ENTITIES }} from '../config/entities.js';

// {e.plural_label}: {e.description or 'records'} (access policy: {e.access})
export default function {comp}() {{
  return <ResourcePage config={{ENTITIES.{e.name}}} />;
}}
"""


def render_app_config(bp: Blueprint, ui_spec: Dict) -> str:
    nav = [{"path": "/", "label": "Dashboard", "adminOnly": False}]
    nav += [{"path": e.ui_path, "label": e.plural_label, "adminOnly": False} for e in bp.entities]
    if bp.has_admin_dashboard:
        nav.append({"path": "/admin", "label": "Admin", "adminOnly": True})
    features = [f for f in bp.features][:10]
    description = ui_spec.get("styling_requirements", {}).get("tagline") or bp.description
    return "\n".join([
        "// Application configuration (generated by FORGE AI UI Agent from ui_spec.json)",
        f"export const APP_NAME = {json.dumps(bp.project_name)};",
        f"export const APP_DESCRIPTION = {json.dumps(description[:240])};",
        f"export const ROLES = {json.dumps(bp.roles)};",
        f"export const FEATURES = {json.dumps(features, indent=2)};",
        f"export const NAV_ITEMS = {json.dumps(nav, indent=2)};",
    ])


def render_entities_config(bp: Blueprint) -> str:
    configs = {e.name: entity_ui_config(e, bp) for e in bp.entities}
    return ("// Entity metadata used by the CRUD pages (generated by FORGE AI UI Agent from ui_spec.json)\n"
            f"export const ENTITIES = {json.dumps(configs, indent=2)};\n")


def render_package_json(bp: Blueprint) -> str:
    return json.dumps({
        "name": bp.slug,
        "private": True,
        "version": "1.0.0",
        "type": "module",
        "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
        "dependencies": FRONTEND_DEPENDENCIES,
        "devDependencies": FRONTEND_DEV_DEPENDENCIES,
    }, indent=2)


VITE_CONFIG = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// During development /api is proxied to the FastAPI backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
});
"""


def write_frontend_files(bp: Blueprint, project: GeneratedProject, ui_spec: Dict) -> List[str]:
    primary = ui_spec.get("styling_requirements", {}).get("primary_color", "#2563eb")
    project.write("frontend/package.json", render_package_json(bp), AGENT)
    project.write("frontend/vite.config.js", VITE_CONFIG, AGENT)
    project.write("frontend/index.html", f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{bp.project_name}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
""", AGENT)
    project.write("frontend/src/main.jsx", MAIN_JSX, AGENT)
    project.write("frontend/src/App.jsx", render_app_jsx(bp), AGENT)
    project.write("frontend/src/styles.css", STYLES_CSS.replace("__PRIMARY__", primary), AGENT)
    project.write("frontend/src/api/client.js", API_CLIENT_JS.replace("__TOKEN_KEY__", f"{bp.slug}_token"), AGENT)
    project.write("frontend/src/config/app.js", render_app_config(bp, ui_spec), AGENT)
    project.write("frontend/src/config/entities.js", render_entities_config(bp), AGENT)
    project.write("frontend/src/utils/format.js", FORMAT_JS, AGENT)
    project.write("frontend/src/components/Layout.jsx", LAYOUT_JSX, AGENT)
    project.write("frontend/src/components/Modal.jsx", MODAL_JSX, AGENT)
    project.write("frontend/src/components/EntityForm.jsx", ENTITY_FORM_JSX, AGENT)
    project.write("frontend/src/components/ResourcePage.jsx", RESOURCE_PAGE_JSX, AGENT)
    project.write("frontend/src/pages/DashboardPage.jsx", DASHBOARD_JSX, AGENT)
    project.write("frontend/src/pages/NotFoundPage.jsx", NOT_FOUND_JSX, AGENT)
    if bp.has_admin_dashboard:
        project.write("frontend/src/pages/AdminPage.jsx", ADMIN_JSX, AGENT)
    for e in bp.entities:
        project.write(f"frontend/src/pages/{page_component_name(e.plural_label)}.jsx", render_entity_page(e), AGENT)
    return project.files_by_agent(AGENT)
