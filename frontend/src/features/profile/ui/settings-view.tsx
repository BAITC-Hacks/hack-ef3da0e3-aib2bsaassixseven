"use client";

import { useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
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
        setMessage("Сессия истекла. Войдите снова.");
        setSaving(false);
        return;
      }
      const { error } = await supabase
        .from("profiles")
        .update({ display_name: draft.displayName })
        .eq("id", user.id);
      if (error) {
        setMessage("Не удалось сохранить профиль.");
        setSaving(false);
        return;
      }
    }

    updateProfile(draft);
    setMessage(
      publicEnv.isSupabaseConfigured
        ? "Профиль сохранён."
        : "Изменения сохранены в демо-сессии.",
    );
    setSaving(false);
  }

  return (
    <div>
      <PageHeader
        description="Личные данные, которые используются в протоколах и поручениях."
        title="Настройки"
      />

      <form className={styles.form} onSubmit={handleSubmit}>
        <section>
          <h2>Профиль</h2>
          <div className={styles.fields}>
            <label>
              Имя
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
              Роль
              <input
                onChange={(event) => updateField("role", event.target.value)}
                value={draft.role}
              />
            </label>
            <label>
              Подразделение
              <input
                onChange={(event) =>
                  updateField("department", event.target.value)
                }
                value={draft.department}
              />
            </label>
          </div>
        </section>

        <section>
          <h2>Предпочтения</h2>
          <label className={styles.checkbox}>
            <input defaultChecked type="checkbox" />
            Показывать поручения без ответственного на Dashboard
          </label>
          <label className={styles.checkbox}>
            <input defaultChecked type="checkbox" />
            Требовать повторного утверждения после любой правки
          </label>
        </section>

        <div className={styles.actions}>
          <button disabled={saving} type="submit">
            {saving ? "Сохраняем…" : "Сохранить изменения"}
          </button>
          <p aria-live="polite">{message}</p>
        </div>
      </form>
    </div>
  );
}
