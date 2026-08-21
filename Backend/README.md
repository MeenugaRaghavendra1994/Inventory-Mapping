# Inventory Mapping Backend

This Next.js service owns the server-side API routes and Supabase service-role access.

## Local setup

1. Copy `.env.example` to `.env.local`.
2. Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `FRONTEND_URL`.
3. Run `npm install` and `npm run dev -- --port 3001`.

Deploy this directory as a separate Vercel project. Set its Vercel project root to `Backend`, then add the same environment variables. Copy the deployed backend URL into the Frontend project's `NEXT_PUBLIC_BACKEND_URL` variable.
