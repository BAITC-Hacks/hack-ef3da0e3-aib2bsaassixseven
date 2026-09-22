"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  UnauthorizedApiError,
  fetchCurrentUser,
  type MeResponse,
} from "@/lib/api";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

type ViewState =
  | { state: "loading" }
  | { state: "ready"; data: MeResponse }
  | { state: "unauthorized" }
  | { state: "offline" };

export function ApiStatus() {
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<ViewState>({ state: "loading" });

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const supabase = createBrowserSupabaseClient();
        const { data } = await supabase.auth.getSession();
        const token = data.session?.access_token;
        if (!token) throw new UnauthorizedApiError();
        const me = await fetchCurrentUser(token);
        if (active) setView({ state: "ready", data: me });
      } catch (error) {
        if (!active) return;
        setView(
          error instanceof UnauthorizedApiError
            ? { state: "unauthorized" }
            : { state: "offline" },
        );
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [attempt]);

  if (view.state === "loading") {
    return (
      <section className="status-card pending" aria-live="polite">
        <span className="status-dot" />
        <div>
          <span className="eyebrow">Connection 01</span>
          <h2>Checking protected API…</h2>
        </div>
      </section>
    );
  }

  if (view.state === "unauthorized") {
    return (
      <section className="status-card error" aria-live="polite">
        <span className="status-dot" />
        <div>
          <span className="eyebrow">Access interrupted</span>
          <h2>Session expired</h2>
          <Link className="text-link" href="/login">
            Sign in again
          </Link>
        </div>
      </section>
    );
  }

  if (view.state === "offline") {
    return (
      <section className="status-card error" aria-live="polite">
        <span className="status-dot" />
        <div>
          <span className="eyebrow">Connection 01</span>
          <h2>FastAPI is offline</h2>
          <p>Start the backend on port 8000, then reconnect.</p>
          <button
            className="secondary-button"
            onClick={() => {
              setView({ state: "loading" });
              setAttempt((value) => value + 1);
            }}
            type="button"
          >
            Retry connection
          </button>
        </div>
      </section>
    );
  }

  const displayName =
    view.data.profile?.display_name || view.data.user.email || "Authenticated user";

  return (
    <section className="status-card success" aria-live="polite">
      <span className="status-dot" />
      <div>
        <span className="eyebrow">Protected API / Online</span>
        <h2>{displayName}</h2>
        <p>{view.data.user.email}</p>
        <dl className="claim-grid">
          <div>
            <dt>Role</dt>
            <dd>{view.data.user.role}</dd>
          </div>
          <div>
            <dt>RLS profile</dt>
            <dd>{view.data.profile ? "resolved" : "pending"}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
