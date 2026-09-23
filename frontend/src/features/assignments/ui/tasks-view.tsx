"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import {
  formatDueDate,
  taskStatusLabel,
} from "@/features/demo-workspace/lib/format";
import type { DemoTaskStatus } from "@/features/demo-workspace/model/demo-data";

import styles from "./tasks-view.module.scss";

export function TasksView() {
  const { meetings, updateTaskStatus } = useDemoWorkspace();
  const [status, setStatus] = useState<"all" | DemoTaskStatus>("all");
  const tasks = useMemo(
    () =>
      meetings
        .flatMap((meeting) =>
          meeting.assignments.map((task) => ({ ...task, meeting })),
        )
        .filter((task) => status === "all" || task.status === status),
    [meetings, status],
  );

  return (
    <div>
      <PageHeader
        description="Поручения из проверенных и черновых протоколов."
        title="Поручения"
      />

      <div className={styles.toolbar}>
        <label>
          Статус
          <select
            onChange={(event) =>
              setStatus(event.target.value as "all" | DemoTaskStatus)
            }
            value={status}
          >
            <option value="all">Все</option>
            <option value="open">Открытые</option>
            <option value="in_progress">В работе</option>
            <option value="completed">Выполненные</option>
          </select>
        </label>
      </div>

      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Поручение</th>
              <th>Ответственный</th>
              <th>Срок</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => (
              <tr key={task.id}>
                <td>
                  <strong>{task.title}</strong>
                  <Link href={`/meetings/${task.meeting.id}`}>
                    {task.meeting.title}
                  </Link>
                </td>
                <td>{task.assignee || "Нужно уточнить"}</td>
                <td>{formatDueDate(task.dueDate)}</td>
                <td>
                  <select
                    aria-label={`Статус поручения ${task.title}`}
                    onChange={(event) =>
                      updateTaskStatus(
                        task.id,
                        event.target.value as DemoTaskStatus,
                      )
                    }
                    value={task.status}
                  >
                    <option value="open">{taskStatusLabel("open")}</option>
                    <option value="in_progress">
                      {taskStatusLabel("in_progress")}
                    </option>
                    <option value="completed">
                      {taskStatusLabel("completed")}
                    </option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {tasks.length === 0 ? (
          <p className={styles.empty}>Поручений с таким статусом нет.</p>
        ) : null}
      </div>
    </div>
  );
}
