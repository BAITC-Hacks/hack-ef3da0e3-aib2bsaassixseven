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
  const { deleteMeeting, meetings } = useDemoWorkspace();
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
        description="Upload, process, review and approve meeting minutes."
        title="Meetings"
      />

      <div className={styles.toolbar}>
        <input
          aria-label="Search meetings"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search"
          type="search"
          value={query}
        />
        <select
          aria-label="Filter by status"
          onChange={(event) =>
            setStatus(event.target.value as "all" | DemoMeetingStatus)
          }
          value={status}
        >
          <option value="all">All statuses</option>
          <option value="queued">Queued</option>
          <option value="processing">Processing</option>
          <option value="review_required">Needs review</option>
          <option value="approved">Approved</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Meeting</th>
              <th>Date</th>
              <th>Participants</th>
              <th>Status</th>
              <th aria-label="Actions" />
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
                      if (window.confirm(`Delete “${meeting.title}”?`)) {
                        deleteMeeting(meeting.id);
                      }
                    }}
                    type="button"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredMeetings.length === 0 ? (
          <div className={styles.empty}>
            <p>No meetings found.</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
