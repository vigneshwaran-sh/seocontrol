# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Frontend Overview

React 19 + TypeScript SPA, built with Vite and Tailwind CSS v4. Serves as the UI for the MissionControl content pipeline platform.

## Commands

```bash
npm run dev      # dev server at http://localhost:5173
npm run build    # tsc type-check + Vite production build (output: dist/)
npm run lint     # ESLint
npm run preview  # serve the production build locally
```

No test suite exists yet. The `VITE_API_URL` env var controls the backend URL (defaults to `http://localhost:8000`).

## Architecture

### Routing
`src/App.tsx` — React Router v7. All routes except `/login` are wrapped in `<ProtectedRoute>` (checks for a JWT in localStorage) then `<Layout>` (sidebar + topbar shell). Admin-only routes (`/users`, `/settings`) are further wrapped in `<RoleGate requiredRole="admin">`.

Route structure:
```
/login                             → Login page
/                                  → Dashboard
/users                             → User management (admin only)
/settings                          → API keys + Notion config (admin only)
/spaces/:spaceId/tasks             → Kanban board
/spaces/:spaceId/docs              → Document list
/spaces/:spaceId/docs/:docId       → TipTap rich-text editor
/spaces/:spaceId/agents            → Pipeline agent grid
/spaces/:spaceId/agents/:agentId   → Agent detail / skill editor
/spaces/:spaceId/logs              → LLM call log viewer
```

### API client
`src/lib/api.ts` — Axios instance with `baseURL` from `VITE_API_URL`. Two interceptors:
- Request: reads `mc_token` from localStorage and attaches `Authorization: Bearer <token>`
- Response: on 401, removes `mc_token` and redirects to `/login`

All API calls go through this singleton. Import it as `import api from '../lib/api'`.

### Global state (Context)
Two React contexts wrap the entire app:

**`AuthContext`** (`src/contexts/AuthContext.tsx`)
- Holds the current `User` object and loading state
- `login()` calls `POST /api/auth/login`, stores token, sets user
- `logout()` clears token and redirects to `/login`
- `fetchUser()` hits `GET /api/auth/me` — call this to refresh user after profile changes
- Consumed via `useAuth()` hook

**`WorkspaceContext`** (`src/contexts/WorkspaceContext.tsx`)
- Loads the first org (or creates one named "My Organization" if none exist) on user login
- Fetches all spaces for that org and exposes them as `spaces[]`
- `refreshSpaces()` re-fetches the space list — call it after creating/deleting a space
- Consumed via `useWorkspace()` hook

### Types
`src/types.ts` — All shared TypeScript interfaces and constants. Key items:
- `Org`, `Space`, `Task`, `Agent`, `Comment`, `Doc`, `Folder`, `TaskStatus`
- `PIPELINE_ROLES` — maps the 4 role keys to display labels/colours
- `PROVIDER_OPTIONS` — `openai`, `gemini`, `claude`
- `PRIORITY_OPTIONS` — `urgent`, `high`, `medium`, `low`, `none`

### Components
`src/components/`:
- `Layout.tsx` — top-level shell with `Sidebar` and `TopBar`; renders `<Outlet />`
- `Sidebar.tsx` — space list + navigation links per space
- `ProtectedRoute.tsx` — redirects to `/login` if no `mc_token` in localStorage
- `RoleGate.tsx` — renders children only if user role matches; otherwise 403 message
- `TaskDetailModal.tsx` — full task editor modal with comments and assignee picker
- `AgentModal.tsx` — create/edit agent form (provider + model picker fetches live model list)
- `CreateSpaceModal.tsx` — space creation form including niche + topic_count fields
- `UserModal.tsx` — create/edit user form

### Pages
- `SpaceTasks.tsx` — Kanban board grouped by `task_status`; drag-and-drop reordering calls `PUT /tasks/:id/move`
- `SpaceAgents.tsx` — shows 4 pipeline agents per space in role order; click → `AgentDetail`
- `AgentDetail.tsx` — provider/model config + TipTap rich text editor for `skill_content` (the agent's instruction manual)
- `LLMLogs.tsx` — filterable table of all LLM calls for a space, showing provider/model/duration/cache status
- `Settings.tsx` — two-tab page: API keys (OpenAI/Gemini/Claude) + Notion integration setup
- `DocEditor.tsx` — TipTap editor for internal knowledge docs

## Key Patterns

- **Auth token**: stored as `mc_token` in localStorage; read by the Axios interceptor on every request.
- **Model fetching**: `AgentModal` calls `GET /api/orgs/{orgId}/settings/providers/{provider}/models` dynamically after a provider is selected — this hits the actual provider API, so it requires a valid API key to be saved first.
- **Notion setup**: the Settings page saves `notion_token` and `notion_database_id`; the backend validates the token against Notion's API before saving.
- **Kanban position**: tasks have a `position` integer per status column; reordering calls `PUT /{task_id}/move` with `{status_id, position}`.
- **Revision count**: the `Task.revision_count` field (mapped from `_revision_count` in MongoDB) is shown in task cards to indicate pipeline loop depth.
