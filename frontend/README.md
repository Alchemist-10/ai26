# Sakshi frontend

React + TypeScript interface for Sakshi, the citywide vehicle tracking and analytics system.

```bash
npm ci
npm run dev
```

Default URL: http://localhost:5174. The development server proxies `/api` to
http://127.0.0.1:8001. See [RUN.md](../RUN.md) for environment variables and
backend setup. `npm run build` checks TypeScript and creates `dist/`;
`npm run lint` runs Oxlint. Production hosting must route `/api` to the backend.
