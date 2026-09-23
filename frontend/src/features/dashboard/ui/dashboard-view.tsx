"use client";

import Link from "next/link";

import { PageHeader } from "@/components/ui/page-header";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import {
  formatDueDate,
  formatMeetingDate,
  meetingStatusLabel,
} from "@/features/demo-workspace/lib/format";

import styles from "./dashboard-view.module.scss";

export function DashboardView() {
  const { meetings, openNewMeeting, profile } = useDemoWorkspace();
  const tasks = meetings.flatMap((meeting) =>
    meeting.assignments.map((task) => ({ ...task, meeting })),
  );
  const openTasks = tasks.filter((task) => task.status !== "completed");
  const reviewCount = meetings.filter(
    (meeting) => meeting.status === "review_required",
  ).length;
  const processingCount = meetings.filter(
    (meeting) => meeting.status === "processing",
  ).length;

  return (
    <div>
      <PageHeader
        action={
          <button className={styles.primaryAction} onClick={openNewMeeting}>
            Новое совещание
          </button>
        }
        description="Совещания, которые требуют внимания, и ближайшие поручения."
        title={`Добрый день, ${profile.displayName}`}
      />

      <section className={styles.summary} aria-label="Краткая сводка">
        <div>
          <strong>{reviewCount}</strong>
          <span>протокола требуют проверки</span>
        </div>
        <div>
          <strong>{processingCount}</strong>
          <span>запись обрабатывается</span>
        </div>
        <div>
          <strong>{openTasks.length}</strong>
          <span>открытых поручений</span>
        </div>
      </section>

      <div className={styles.columns}>
        <section className={styles.section}>
          <header>
            <h2>Последние совещания</h2>
            <Link href="/meetings">Все совещания</Link>
          </header>
          <div className={styles.meetingList}>
            {meetings.slice(0, 4).map((meeting) => (
              <Link href={`/meetings/${meeting.id}`} key={meeting.id}>
                <div>
                  <strong>{meeting.title}</strong>
                  <span>{formatMeetingDate(meeting.recordedAt)}</span>
                </div>
                <span data-status={meeting.status}>
                  {meetingStatusLabel(meeting.status)}
                </span>
              </Link>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <header>
            <h2>Ближайшие поручения</h2>
            <Link href="/tasks">Все поручения</Link>
          </header>
          <div className={styles.taskList}>
            {openTasks.slice(0, 5).map((task) => (
              <Link href={`/meetings/${task.meeting.id}`} key={task.id}>
                <strong>{task.title}</strong>
                <span>
                  {task.assignee || "Ответственный не указан"} ·{" "}
                  {formatDueDate(task.dueDate)}
                </span>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <p className={styles.demoNotice}>
        Демо-данные хранятся только в памяти браузера до подключения meeting API.
      </p>
    </div>
  );
}
