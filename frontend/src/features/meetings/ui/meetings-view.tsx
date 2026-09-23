"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import { formatMeetingDate, meetingStatusLabel } from "@/features/demo-workspace/lib/format";
import type { DemoMeeting, DemoMeetingStatus } from "@/features/demo-workspace/model/demo-data";
import { deleteMeeting as deleteApiMeeting } from "@/features/meetings/api/client";
import { useMeetingsQuery } from "@/features/meetings/api/hooks";
import type { Meeting } from "@/features/meetings/api/schemas";

import styles from "./meetings-view.module.scss";

export function MeetingsView() {
  const workspace = useDemoWorkspace();
  return workspace.isDemo ? (
    <MeetingsTable meetings={workspace.meetings} onDelete={workspace.deleteMeeting} />
  ) : <LiveMeetingsView />;
}

function LiveMeetingsView() {
  const query = useMeetingsQuery();
  const [error, setError] = useState("");
  if (query.isPending) return <p role="status">Loading meetings…</p>;
  if (query.error) return <p role="alert">The meeting service could not be reached.</p>;
  return <><p aria-live="polite">{error}</p><MeetingsTable meetings={query.data.items} onDelete={async (id) => {
    setError("");
    try { await deleteApiMeeting(id); await query.refetch(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The meeting could not be deleted."); }
  }} /></>;
}

function MeetingsTable({ meetings, onDelete }: { meetings: Array<DemoMeeting | Meeting>; onDelete: (id: string) => void | Promise<void> }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | DemoMeetingStatus>("all");
  const filteredMeetings = useMemo(() => meetings.filter((meeting) => meeting.title.toLowerCase().includes(query.toLowerCase()) && (status === "all" || meeting.status === status)), [meetings, query, status]);
  return <div>
    <PageHeader description="Upload, process, review and approve meeting minutes." title="Meetings" />
    <div className={styles.toolbar}><input aria-label="Search meetings" onChange={(event) => setQuery(event.target.value)} placeholder="Search" type="search" value={query} /><select aria-label="Filter by status" onChange={(event) => setStatus(event.target.value as "all" | DemoMeetingStatus)} value={status}><option value="all">All statuses</option><option value="queued">Queued</option><option value="processing">Processing</option><option value="review_required">Needs review</option><option value="approved">Approved</option><option value="failed">Failed</option></select></div>
    <div className={styles.tableWrap}><table><thead><tr><th>Meeting</th><th>Date</th><th>Participants</th><th>Status</th><th aria-label="Actions" /></tr></thead><tbody>{filteredMeetings.map((meeting) => {
      const demo = "recordedAt" in meeting;
      return <tr key={meeting.id}><td><Link href={`/meetings/${meeting.id}`}>{meeting.title}</Link><span>{demo ? meeting.audioFileName : meeting.source.kind === "uploaded_audio" ? "Uploaded recording" : "Browser recording"}</span></td><td>{demo ? formatMeetingDate(meeting.recordedAt) : meeting.meeting_date}</td><td>{demo ? meeting.participantNames.length || "—" : meeting.participants.length || "—"}</td><td data-status={meeting.status}>{meetingStatusLabel(meeting.status)}</td><td><button onClick={() => { if (window.confirm(`Delete “${meeting.title}”?`)) void onDelete(meeting.id); }} type="button">Delete</button></td></tr>;
    })}</tbody></table>{filteredMeetings.length === 0 ? <div className={styles.empty}><p>No meetings found.</p></div> : null}</div>
  </div>;
}
