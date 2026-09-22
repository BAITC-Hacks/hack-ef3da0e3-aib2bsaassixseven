import Link from "next/link";

const stack = [
  {
    index: "01",
    name: "Next.js",
    role: "Interface + Auth",
    detail: "App Router, Supabase SSR sessions, and a focused build surface.",
    accent: "cyan",
  },
  {
    index: "02",
    name: "FastAPI",
    role: "Protected business API",
    detail: "Typed endpoints that verify every Supabase access token.",
    accent: "lime",
  },
  {
    index: "03",
    name: "Supabase",
    role: "Identity + Postgres",
    detail: "Auth, profiles, and row-level security without a service key.",
    accent: "violet",
  },
] as const;

export default function Home() {
  return (
    <main id="main">
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Hackalem home">
          <span className="wordmark-mark">H</span>
          <span>HACKALEM</span>
        </Link>
        <nav aria-label="Primary navigation">
          <a href="#stack">Stack</a>
          <a href="#setup">Setup</a>
          <Link className="nav-action" href="/login">
            Sign in <span aria-hidden="true">↗</span>
          </Link>
        </nav>
      </header>

      <section className="hero-section" aria-labelledby="hero-title">
        <div className="hero-meta">
          <span className="live-dot" aria-hidden="true" />
          <span>Hackathon system / Ready</span>
          <span className="hero-coordinate">42.3417° N · 69.5901° E</span>
        </div>

        <div className="hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">FastAPI × Next.js × Supabase</p>
            <h1 aria-label="Ship before the clock runs out." id="hero-title">
              Ship before the
              <br />
              <span>clock runs out.</span>
            </h1>
            <p className="hero-description">
              A secure full-stack launchpad with authentication, protected API
              routes, and database policies already wired together.
            </p>
            <div className="hero-actions">
              <Link className="primary-button" href="/dashboard">
                Open dashboard <span aria-hidden="true">→</span>
              </Link>
              <a className="secondary-button" href="#setup">
                Configure Supabase
              </a>
            </div>
          </div>

          <div className="system-panel" aria-label="Request architecture">
            <div className="panel-label">
              <span>REQUEST PATH</span>
              <span>01—04</span>
            </div>
            <div className="system-flow">
              <div className="system-node">
                <span>01</span>
                <strong>Next.js</strong>
                <small>SESSION OWNER</small>
              </div>
              <div className="flow-arrow" aria-hidden="true">↓</div>
              <div className="system-token">
                <span>Bearer</span>
                <code>eyJhbGciOi...</code>
              </div>
              <div className="flow-arrow" aria-hidden="true">↓</div>
              <div className="system-node highlighted">
                <span>02</span>
                <strong>FastAPI</strong>
                <small>VERIFY JWT</small>
              </div>
              <div className="flow-arrow" aria-hidden="true">↓</div>
              <div className="system-node">
                <span>03</span>
                <strong>Supabase</strong>
                <small>RLS ENFORCED</small>
              </div>
            </div>
            <div className="panel-status">
              <span className="status-pulse" />
              User-scoped from browser to row
            </div>
          </div>
        </div>
      </section>

      <section className="stack-section" id="stack" aria-labelledby="stack-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">System modules</p>
            <h2 id="stack-title">Three tools. One path.</h2>
          </div>
          <p>Minimal moving parts for a team moving at maximum speed.</p>
        </div>
        <div className="stack-grid">
          {stack.map((item) => (
            <article className={`stack-card ${item.accent}`} key={item.name}>
              <span className="card-index">[{item.index}]</span>
              <div className="card-sigil" aria-hidden="true">
                {item.name.charAt(0)}
              </div>
              <p>{item.role}</p>
              <h3>{item.name}</h3>
              <p className="card-detail">{item.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="setup-section" id="setup" aria-labelledby="setup-title">
        <div className="setup-intro">
          <p className="eyebrow">Launch sequence</p>
          <h2 id="setup-title">From clone to first request.</h2>
          <p>Bring your own Supabase project. The rest of the route is marked.</p>
        </div>
        <ol className="setup-list">
          <li>
            <span>01</span>
            <div><strong>Copy environment files</strong><code>cp .env.example .env</code></div>
          </li>
          <li>
            <span>02</span>
            <div><strong>Add Supabase credentials</strong><small>Project URL + publishable key</small></div>
          </li>
          <li>
            <span>03</span>
            <div><strong>Start both applications</strong><code>./scripts/dev.ps1</code></div>
          </li>
        </ol>
      </section>

      <footer>
        <span>HACKALEM / STARTER 01</span>
        <span>BUILD SOMETHING PEOPLE WANT.</span>
      </footer>
    </main>
  );
}
