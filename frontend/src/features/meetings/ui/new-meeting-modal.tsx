"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";

import styles from "./new-meeting-modal.module.scss";

const maxFileSize = 100 * 1024 * 1024;

export function NewMeetingModal() {
  const router = useRouter();
  const { closeNewMeeting, createMeeting, isNewMeetingOpen } = useDemoWorkspace();
  const formRef = useRef<HTMLFormElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isNewMeetingOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    titleRef.current?.focus();

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeNewMeeting();
    };
    window.addEventListener("keydown", closeOnEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [closeNewMeeting, isNewMeetingOpen]);

  if (!isNewMeetingOpen) return null;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const formData = new FormData(event.currentTarget);
    const file = formData.get("recording");

    if (!(file instanceof File) || file.size === 0) {
      setError("Выберите аудио- или видеофайл встречи.");
      return;
    }
    if (file.size > maxFileSize) {
      setError("Файл превышает лимит 100 MiB.");
      return;
    }

    const participantNames = String(formData.get("participants") ?? "")
      .split(/[\n,]/)
      .map((name) => name.trim())
      .filter(Boolean);
    const id = createMeeting({
      title: String(formData.get("title") ?? "").trim(),
      recordedAt: String(formData.get("recordedAt") ?? ""),
      language: String(formData.get("language") ?? "auto") as
        | "auto"
        | "ru"
        | "kk"
        | "mixed",
      participantNames,
      audioFileName: file.name,
    });

    formRef.current?.reset();
    closeNewMeeting();
    router.push(`/meetings/${id}`);
  }

  return (
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) closeNewMeeting();
      }}
    >
      <section
        aria-labelledby="new-meeting-title"
        aria-modal="true"
        className={styles.modal}
        role="dialog"
      >
        <header className={styles.header}>
          <div>
            <h2 id="new-meeting-title">Новое совещание</h2>
            <p>Добавьте запись и контекст для точного протокола.</p>
          </div>
          <button
            aria-label="Закрыть"
            className={styles.close}
            onClick={closeNewMeeting}
            type="button"
          >
            ×
          </button>
        </header>

        <form className={styles.form} onSubmit={handleSubmit} ref={formRef}>
          <div className={styles.columns}>
            <label className={styles.fullWidth}>
              Название встречи
              <input
                name="title"
                placeholder="Еженедельный продуктовый синк"
                ref={titleRef}
                required
                type="text"
              />
            </label>
            <label>
              Дата и время
              <input name="recordedAt" required type="datetime-local" />
            </label>
            <label>
              Язык
              <select defaultValue="auto" name="language">
                <option value="auto">Автоопределение</option>
                <option value="ru">Русский</option>
                <option value="kk">Қазақша</option>
                <option value="mixed">Смешанный</option>
              </select>
            </label>
            <label className={styles.fullWidth}>
              Участники
              <textarea
                name="participants"
                placeholder="По одному имени в строке"
                rows={3}
              />
            </label>
            <label className={styles.fullWidth}>
              Запись встречи
              <input
                accept=".wav,.mp3,.m4a,.ogg,.webm,audio/*,video/webm"
                name="recording"
                required
                type="file"
              />
              <span>WAV, MP3, M4A, OGG или WebM · до 100 MiB</span>
            </label>
          </div>

          <label className={styles.consent}>
            <input name="consent" required type="checkbox" />
            Участники уведомлены о записи и AI-транскрибации.
          </label>

          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}

          <footer className={styles.footer}>
            <button onClick={closeNewMeeting} type="button">
              Отмена
            </button>
            <button className={styles.primary} type="submit">
              Начать обработку
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
