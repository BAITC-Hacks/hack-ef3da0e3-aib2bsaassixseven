"use client";

import { useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { signOut } from "@/features/auth/actions";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import type { DemoProfile } from "@/features/demo-workspace/model/demo-data";
import { publicEnv } from "@/lib/config/public-env";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

import styles from "./settings-view.module.scss";

export function SettingsView() {
  const { profile, updateProfile } = useDemoWorkspace();
  const [draft, setDraft] = useState(profile);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  function updateField(field: keyof DemoProfile, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");

    if (publicEnv.isSupabaseConfigured) {
      const supabase = createBrowserSupabaseClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (!user) {
        setMessage("Your session has expired. Sign in again.");
        setSaving(false);
        return;
      }
      const { error } = await supabase
        .from("profiles")
        .update({ display_name: draft.displayName })
        .eq("id", user.id);
      if (error) {
        setMessage("We couldn't save your profile.");
        setSaving(false);
        return;
      }
    }

    updateProfile(draft);
    setMessage(
      publicEnv.isSupabaseConfigured
        ? "Profile saved."
        : "Changes saved for this demo session.",
    );
    setSaving(false);
  }

  return (
    <div>
      <PageHeader
        description="Manage the personal details used in meeting minutes and assignments."
        title="Profile"
      />

      <form className={styles.form} onSubmit={handleSubmit}>
        <section>
          <h2>Personal information</h2>
          <div className={styles.fields}>
            <label>
              Name
              <input
                onChange={(event) =>
                  updateField("displayName", event.target.value)
                }
                required
                value={draft.displayName}
              />
            </label>
            <label>
              Email
              <input disabled type="email" value={draft.email} />
            </label>
            <label>
              Role
              <input
                onChange={(event) => updateField("role", event.target.value)}
                value={draft.role}
              />
            </label>
            <label>
              Department
              <input
                onChange={(event) =>
                  updateField("department", event.target.value)
                }
                value={draft.department}
              />
            </label>
          </div>
        </section>

        <div className={styles.actions}>
          <button disabled={saving} type="submit">
            {saving ? "Saving…" : "Save changes"}
          </button>
          <p aria-live="polite">{message}</p>
        </div>
      </form>

      <form action={signOut} className={styles.signOut}>
        <div>
          <h2>Session</h2>
          <p>Sign out of Tirke on this device.</p>
        </div>
        <button type="submit">Sign out</button>
      </form>
    </div>
  );
}
