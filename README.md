# Singapore Defense Tech Hackathon

The current application is Singapore Canvas, a Cesium-based 3D viewer. All application source, configuration, assets, and frontend documentation live in [`frontend/`](frontend/). No backend is implemented yet.

## Run locally

Use Node.js 22.12 or later.

```sh
cd frontend
npm ci
cp .env.example .env.local
# Configure the credentials in .env.local.
npm run dev
```

From `frontend/`, run `npm run build` to build the demo or `npm run build:lib` to build the reusable library.

See the [codebase summary](frontend/CODEBASE-SUMMARY.md) for architecture and setup details, and the [API design](frontend/docs/API-DESIGN.md) for implemented and planned features.
