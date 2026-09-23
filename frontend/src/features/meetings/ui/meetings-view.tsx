"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import {
  formatMeetingDate,
  meetingStatusLabel,
} from "@/features/demo-workspace/lib/format";
import type { DemoMeetingStatus } from "@/features/demo-workspace/model/demo-data";

import styles from "./meetings-view.module.scss";

export function MeetingsView() {
  const { deleteMeeting, meetings, openNewMeeting } = useDemoWorkspace();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | DemoMeetingStatus>("all");
  const filteredMeetings = useMemo(
    () =>
      meetings.filter(
        (meeting) =>
          meeting.title.toLowerCase().includes(query.toLowerCase()) &&
          (status === "all" || meeting.status === status),
      ),
    [meetings, query, status],
  );

  return (
    <div>
      <PageHeader
        action={
          <button className={styles.primaryAction} onClick={openNewMeeting}>
            Новое совещание
          </button>
        }
        description="Загрузки, обработка, проверка и утверждённые протоколы."
        title="Совещания"
      />

      <div className={styles.toolbar}>
        <input
          aria-label="Поиск совещаний"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Поиск по названию"
          type="search"
          value={query}
        />
        <select
          aria-label="Фильтр по статусу"
          onChange={(event) =>
            setStatus(event.target.value as "all" | DemoMeetingStatus)
          }
          value={status}
        >
          <option value="all">Все статусы</option>
          <option value="processing">Обработка</option>
          <option value="review_required">Нужна проверка</option>
          <option value="approved">Утверждено</option>
          <option value="failed">Ошибка</option>
        </select>
      </div>

      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Совещание</th>
              <th>Дата</th>
              <th>Участники</th>
              <th>Статус</th>
              <th aria-label="Действия" />
            </tr>
          </thead>
          <tbody>
            {filteredMeetings.map((meeting) => (
              <tr key={meeting.id}>
                <td>
                  <Link href={`/meetings/${meeting.id}`}>{meeting.title}</Link>
                  <span>{meeting.audioFileName}</span>
                </td>
                <td>{formatMeetingDate(meeting.recordedAt)}</td>
                <td>{meeting.participantNames.length || "—"}</td>
                <td data-status={meeting.status}>
                  {meetingStatusLabel(meeting.status)}
                </td>
                <td>
                  <button
                    onClick={() => {
                      if (window.confirm(`Удалить «${meeting.title}»?`)) {
                        deleteMeeting(meeting.id);
                      }
                    }}
                    type="button"
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredMeetings.length === 0 ? (
          <div className={styles.empty}>
            <p>Совещания не найдены.</p>
            <button onClick={openNewMeeting}>Добавить запись</button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
