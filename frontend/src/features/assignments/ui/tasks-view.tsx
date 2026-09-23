"use client";

import { useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import {
  formatDueDate,
  taskStatusLabel,
} from "@/features/demo-workspace/lib/format";
import type { DemoTaskStatus } from "@/features/demo-workspace/model/demo-data";
import { getInsights, getTranscript } from "@/features/meetings/api/client";
import {
  meetingQueryKeys,
  useMeetingsQuery,
} from "@/features/meetings/api/hooks";

import styles from "./tasks-view.module.scss";

export function TasksView() {
  const { isDemo } = useDemoWorkspace();
  return isDemo ? <DemoTasksView /> : <LiveTasksView />;
}

function DemoTasksView() {
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
        description="Assignments from approved and draft meeting minutes."
        title="Assignments"
      />

      <div className={styles.toolbar}>
        <label>
          Status
          <select
            onChange={(event) =>
              setStatus(event.target.value as "all" | DemoTaskStatus)
            }
            value={status}
          >
            <option value="all">All</option>
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
          </select>
        </label>
      </div>

      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Assignment</th>
              <th>Assignee</th>
              <th>Deadline</th>
              <th>Status</th>
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
                <td>{task.assignee || "Needs review"}</td>
                <td>{formatDueDate(task.dueDate)}</td>
                <td>
                  <select
                    aria-label={`Status for ${task.title}`}
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
          <p className={styles.empty}>No assignments match this status.</p>
        ) : null}
      </div>
    </div>
  );
}

function LiveTasksView() {
  const meetingsQuery = useMeetingsQuery();
  const readyMeetings = (meetingsQuery.data?.items ?? []).filter(
    (meeting) =>
      meeting.status === "review_required" || meeting.status === "approved",
  );
  const insightQueries = useQueries({
    queries: readyMeetings.map((meeting) => ({
      queryKey: meetingQueryKeys.insights(meeting.id),
      queryFn: () => getInsights(meeting.id),
    })),
  });
  const transcriptQueries = useQueries({
    queries: readyMeetings.map((meeting) => ({
      queryKey: meetingQueryKeys.transcript(meeting.id),
      queryFn: () => getTranscript(meeting.id),
    })),
  });

  if (meetingsQuery.isPending) {
    return <p role="status">Loading assignments…</p>;
  }
  if (meetingsQuery.error) {
    return <p role="alert">The meeting service could not be reached.</p>;
  }

  const tasks = readyMeetings.flatMap((meeting, index) =>
    (insightQueries[index]?.data?.action_items ?? []).map((task) => ({
      ...task,
      meeting,
      assigneeDisplayName: task.assignee_speaker_id
        ? transcriptQueries[index]?.data?.speakers.find(
            (speaker) => speaker.speaker_id === task.assignee_speaker_id,
          )?.display_name
        : null,
    })),
  );
  const loading = [...insightQueries, ...transcriptQueries].some(
    (query) => query.isPending,
  );
  const failed = [...insightQueries, ...transcriptQueries].some(
    (query) => query.error,
  );

  return (
    <div>
      <PageHeader
        description="Assignments from saved meeting minutes. Edit them in the meeting review."
        title="Assignments"
      />
      {loading ? <p role="status">Loading saved assignments…</p> : null}
      {failed ? (
        <p role="alert">Some saved assignments could not be loaded.</p>
      ) : null}
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Assignment</th>
              <th>Assignee</th>
              <th>Deadline</th>
              <th>Meeting status</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => (
              <tr key={`${task.meeting.id}-${task.id}`}>
                <td>
                  <strong>{task.text}</strong>
                  <Link href={`/meetings/${task.meeting.id}`}>
                    {task.meeting.title}
                  </Link>
                </td>
                <td>
                  {task.assignee_name ??
                    task.assigneeDisplayName ??
                    "Needs review"}
                </td>
                <td>{task.due_date ?? task.due_date_text ?? "Needs review"}</td>
                <td>
                  {task.meeting.status === "approved"
                    ? "Approved"
                    : "Needs review"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && tasks.length === 0 && !failed ? (
          <p className={styles.empty}>No saved assignments yet.</p>
        ) : null}
      </div>
    </div>
  );
}
