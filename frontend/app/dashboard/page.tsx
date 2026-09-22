import Link from "next/link";
import { redirect } from "next/navigation";

import { signOut } from "@/app/auth/actions";
import { ApiStatus } from "@/components/api-status";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createServerSupabaseClient();
  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims;

  if (!claims?.sub) {
    redirect("/login");
    return null;
  }

  const email =
    typeof claims.email === "string"
      ? claims.email
      : "Authenticated builder";

  return (
    <main className="dashboard-shell" id="main">
      <header className="dashboard-header">
        <Link className="wordmark" href="/" aria-label="Hackalem home">
          <span className="wordmark-mark">H</span>
          <span>HACKALEM</span>
        </Link>
        <div className="account-strip">
          <span className="status-pulse" aria-hidden="true" />
          <span>{email}</span>
          <form action={signOut}>
            <button className="text-button" type="submit">Sign out</button>
          </form>
        </div>
      </header>

      <section className="dashboard-hero">
        <div>
          <p className="eyebrow">Command surface / Authenticated</p>
          <h1>Build room</h1>
          <p>Identity is verified. The protected data path is ready to test.</p>
        </div>
        <div className="clock-block" aria-label="Hackathon status">
          <span>STATUS</span>
          <strong>SHIP MODE</strong>
        </div>
      </section>

      <section className="dashboard-grid" aria-label="Application status">
        <ApiStatus />
        <article className="work-card">
          <div className="panel-label">
            <span>MODULE 02</span>
            <span>READY</span>
          </div>
          <p className="eyebrow">Your feature starts here</p>
          <h2>Replace this module with the thing that wins.</h2>
          <p>
            Authentication and infrastructure are deliberately finished. Keep
            the next commit close to the user problem.
          </p>
          <div className="work-prompt">
            <span>Next move</span>
            <strong>Build one complete user journey</strong>
          </div>
        </article>
      </section>

      <aside className="architecture-strip" aria-label="Current request path">
        <span>Browser</span><b>→</b><span>Supabase Auth</span><b>→</b>
        <span>FastAPI JWT</span><b>→</b><span>Postgres RLS</span>
      </aside>
    </main>
  );
}
