# Inventory Mapping Backend

This Vercel Python service owns the server-side API routes, Pandas calculation, and Supabase service-role access.

## Local setup

1. Copy `.env.example` to `.env.local`.
2. Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `FRONTEND_URL`.
3. Install dependencies with `pip install -r requirements.txt`.

Deploy this directory as a separate Vercel project. Set its Vercel project root to `Backend`, then add the same environment variables. Vercel will discover the Python functions in `api/`. Copy the deployed backend URL into the Frontend project's `NEXT_PUBLIC_BACKEND_URL` variable.
