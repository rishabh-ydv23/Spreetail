Frontend (React + Vite)

Quick start:

```bash
cd frontend
npm install
npm run dev
```

Notes:
- Update `DEFAULT_GROUP_ID` in `src/pages/ImportPage.jsx` to a valid group UUID from the backend, or extend the UI to select a group.
- The frontend expects the backend available at the same host under `/api/v1/`. If backend is at a different origin, configure `vite` proxy in `vite.config.js`.
