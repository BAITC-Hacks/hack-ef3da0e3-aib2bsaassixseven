"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import {
  formatMeetingDate,
  meetingStatusLabel,
} from "@/features/demo-workspace/lib/format";
import type {
  DemoAssignment,
  DemoMeeting,
} from "@/features/demo-workspace/model/demo-data";

import styles from "./meeting-detail-view.module.scss";

function emptyAssignment(): DemoAssignment {
  return {
    id: crypto.randomUUID(),
    title: "",
    assignee: null,
    dueDate: null,
    status: "open",
    evidence: "Добавлено вручную",
    time: "—",
  };
}

export function MeetingDetailView({ meetingId }: { meetingId: string }) {
  const router = useRouter();
  const {
    approveMeeting,
    deleteMeeting,
    meetings,
    saveReview,
  } = useDemoWorkspace();
  const meeting = meetings.find((item) => item.id === meetingId);
  const [draftOverride, setDraft] = useState<DemoMeeting | null>(null);
  const [editingOverride, setIsEditing] = useState<boolean | null>(null);
  const [message, setMessage] = useState("");
  const draft = draftOverride ?? meeting ?? null;
  const isEditing =
    editingOverride ?? (meeting?.status === "review_required");

  const missingFields = useMemo(
    () =>
      draft?.assignments.filter(
        (task) => !task.assignee || !task.dueDate || !task.title.trim(),
      ).length ?? 0,
    [draft],
  );

  if (!meeting || !draft) {
    return (
      <div className={styles.notFound}>
        <h1>Совещание не найдено</h1>
        <p>Возможно, оно было удалено из текущей демо-сессии.</p>
        <Link href="/meetings">Вернуться к совещаниям</Link>
      </div>
    );
  }

  if (meeting.status === "processing" || meeting.status === "queued") {
    return (
      <div className={styles.processing}>
        <Link href="/meetings">← Совещания</Link>
        <h1>{meeting.title}</h1>
        <p aria-live="polite">
          {meeting.processingStage || "Задача ожидает обработки"}
        </p>
        <ol>
          <li data-complete>Файл принят</li>
          <li data-active>Локальная обработка записи</li>
          <li>Проверка протокола</li>
          <li>Утверждение и PDF</li>
        </ol>
        <p className={styles.processingNote}>
          Можно перейти в другой раздел — обработка продолжится в фоне.
        </p>
      </div>
    );
  }

  function saveDraft() {
    if (!draft) return;
    saveReview(meetingId, {
      title: draft.title,
      summary: draft.summary,
      transcript: draft.transcript,
      assignments: draft.assignments,
    });
    setMessage("Изменения сохранены. Протокол требует утверждения.");
  }

  function approveDraft() {
    saveDraft();
    approveMeeting(meetingId);
    setIsEditing(false);
    setMessage("Протокол утверждён и готов к экспорту.");
  }

  async function shareMeeting() {
    if (!draft) return;
    const url = window.location.href;
    if (navigator.share) {
      await navigator.share({ title: draft.title, url }).catch(() => undefined);
      return;
    }
    await navigator.clipboard.writeText(url);
    setMessage("Ссылка скопирована.");
  }

  return (
    <article className={styles.detail}>
      <nav className={styles.breadcrumb} aria-label="Хлебные крошки">
        <Link href="/meetings">Совещания</Link>
        <span>/</span>
        <span>{draft.title}</span>
      </nav>

      <header className={styles.titleBar}>
        <div>
          {isEditing ? (
            <input
              aria-label="Название совещания"
              className={styles.titleInput}
              onChange={(event) =>
                setDraft({ ...draft, title: event.target.value })
              }
              value={draft.title}
            />
          ) : (
            <h1>{draft.title}</h1>
          )}
          <p>
            {formatMeetingDate(draft.recordedAt)} · {draft.duration || "—"} ·{" "}
            {draft.participantNames.length} участника
          </p>
        </div>
        <strong data-status={meeting.status}>
          {meetingStatusLabel(meeting.status)}
        </strong>
      </header>

      <div className={styles.actions}>
        {meeting.status === "approved" && !isEditing ? (
          <button onClick={() => setIsEditing(true)} type="button">
            Редактировать
          </button>
        ) : null}
        {isEditing ? (
          <button onClick={saveDraft} type="button">
            Сохранить
          </button>
        ) : null}
        <button onClick={shareMeeting} type="button">
          Поделиться
        </button>
        <button
          disabled={meeting.status !== "approved"}
          onClick={() => window.print()}
          type="button"
        >
          Скачать PDF
        </button>
        <button
          className={styles.delete}
          onClick={() => {
            if (window.confirm(`Удалить «${meeting.title}»?`)) {
              deleteMeeting(meeting.id);
              router.push("/meetings");
            }
          }}
          type="button"
        >
          Удалить
        </button>
      </div>

      {message ? (
        <p aria-live="polite" className={styles.message}>
          {message}
        </p>
      ) : null}

      {missingFields > 0 ? (
        <p className={styles.warning} role="status">
          {missingFields} поручения содержат пустого ответственного или срок.
          Это допустимо, но требует проверки перед утверждением.
        </p>
      ) : null}

      <section className={styles.section}>
        <h2>Краткое содержание</h2>
        {isEditing ? (
          <textarea
            onChange={(event) =>
              setDraft({ ...draft, summary: event.target.value })
            }
            rows={5}
            value={draft.summary}
          />
        ) : (
          <p>{draft.summary}</p>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2>Поручения</h2>
          {isEditing ? (
            <button
              onClick={() =>
                setDraft({
                  ...draft,
                  assignments: [...draft.assignments, emptyAssignment()],
                })
              }
              type="button"
            >
              + Добавить поручение
            </button>
          ) : null}
        </div>
        <div className={styles.assignmentList}>
          {draft.assignments.map((task, index) => (
            <div className={styles.assignment} key={task.id}>
              {isEditing ? (
                <>
                  <label className={styles.assignmentTitle}>
                    Поручение
                    <input
                      onChange={(event) => {
                        const assignments = [...draft.assignments];
                        assignments[index] = {
                          ...task,
                          title: event.target.value,
                        };
                        setDraft({ ...draft, assignments });
                      }}
                      value={task.title}
                    />
                  </label>
                  <label>
                    Ответственный
                    <input
                      onChange={(event) => {
                        const assignments = [...draft.assignments];
                        assignments[index] = {
                          ...task,
                          assignee: event.target.value || null,
                        };
                        setDraft({ ...draft, assignments });
                      }}
                      value={task.assignee || ""}
                    />
                  </label>
                  <label>
                    Срок
                    <input
                      onChange={(event) => {
                        const assignments = [...draft.assignments];
                        assignments[index] = {
                          ...task,
                          dueDate: event.target.value || null,
                        };
                        setDraft({ ...draft, assignments });
                      }}
                      type="date"
                      value={task.dueDate || ""}
                    />
                  </label>
                  <button
                    className={styles.removeTask}
                    onClick={() =>
                      setDraft({
                        ...draft,
                        assignments: draft.assignments.filter(
                          (item) => item.id !== task.id,
                        ),
                      })
                    }
                    type="button"
                  >
                    Удалить
                  </button>
                </>
              ) : (
                <>
                  <strong>{task.title}</strong>
                  <span>{task.assignee || "Ответственный не указан"}</span>
                  <span>{task.dueDate || "Срок не указан"}</span>
                </>
              )}
              <p>
                <span>{task.time}</span> “{task.evidence}”
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h2>Транскрипт</h2>
        <div className={styles.transcript}>
          {draft.transcript.map((segment, index) => (
            <div key={segment.id}>
              <header>
                <strong>{segment.speaker}</strong>
                <span>{segment.time}</span>
              </header>
              {isEditing ? (
                <textarea
                  aria-label={`Реплика ${segment.speaker} ${segment.time}`}
                  onChange={(event) => {
                    const transcript = [...draft.transcript];
                    transcript[index] = {
                      ...segment,
                      text: event.target.value,
                    };
                    setDraft({ ...draft, transcript });
                  }}
                  rows={3}
                  value={segment.text}
                />
              ) : (
                <p>{segment.text}</p>
              )}
            </div>
          ))}
        </div>
      </section>

      {isEditing ? (
        <footer className={styles.approvalBar}>
          <div>
            <strong>Проверьте результат перед утверждением</strong>
            <span>Новая правка снова потребует подтверждения.</span>
          </div>
          <button onClick={approveDraft} type="button">
            Утвердить протокол
          </button>
        </footer>
      ) : null}
    </article>
  );
}
