import Link from "next/link";

import { AuthForm } from "@/components/auth-form";
import { getPublicEnv } from "@/lib/env";

export default function LoginPage() {
  const env = getPublicEnv();

  return (
    <main className="auth-shell" id="main">
      <Link className="text-link back-link" href="/">
        ← Back to launchpad
      </Link>
      <section className="auth-layout" aria-labelledby="auth-title">
        <div className="auth-copy">
          <span className="eyebrow">Secure entry / Supabase Auth</span>
          <h1 id="auth-title">Join the build room.</h1>
          <p>
            One account connects the Next.js interface to protected FastAPI
            routes and RLS-scoped data.
          </p>
          {!env.isSupabaseConfigured && (
            <p className="config-notice" role="status">
              Add Supabase values to <code>.env.local</code> before signing in.
            </p>
          )}
        </div>
        <AuthForm />
      </section>
    </main>
  );
}
