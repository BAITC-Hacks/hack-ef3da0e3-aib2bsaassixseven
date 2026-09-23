"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import {
  approveMeeting,
  downloadMeetingPdf,
  MeetingApiError,
  retryMeeting,
  updateReview,
} from "@/features/meetings/api/client";
import {
  meetingQueryKeys,
  useMeetingQuery,
  useMeetingResultsQuery,
} from "@/features/meetings/api/hooks";
import type { TranscriptSpeaker } from "@/features/meetings/api/schemas";
import { meetingStatusLabel } from "@/features/demo-workspace/lib/format";

import styles from "./meeting-detail-view.module.scss";

const stageLabels = {
  uploading_to_gpu: "Sending the recording to the processing server",
  ingesting: "Preparing the recording",
  transcribing: "Transcribing speech",
  diarizing: "Separating speakers",
  analyzing: "Extracting key facts, decisions and tasks",
  saving_results: "Saving verified results",
  exporting: "Preparing the PDF",
} as const;

function timestamp(milliseconds: number) {
  const seconds = Math.floor(milliseconds / 1_000);
  const hours = Math.floor(seconds / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  const remainder = seconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function errorMessage(error: unknown) {
  return error instanceof MeetingApiError
    ? error.message
    : "The meeting service could not complete the request.";
}

export function LiveMeetingDetailView({ meetingId }: { meetingId: string }) {
  const queryClient = useQueryClient();
  const meetingQuery = useMeetingQuery(meetingId);
  const meeting = meetingQuery.data;
  const ready =
    meeting?.status === "review_required" || meeting?.status === "approved";
  const results = useMeetingResultsQuery(meetingId, ready);
  const transcript = results.transcript.data;
  const insights = results.insights.data;
  const [activeTab, setActiveTab] = useState<"summary" | "tasks" | "transcript">(
    "summary",
  );
  const [mappingOverride, setMappingOverride] = useState<TranscriptSpeaker[] | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const mappings = mappingOverride ?? transcript?.speakers ?? null;

  const segments = useMemo(
    () => new Map(transcript?.segments.map((segment) => [segment.id, segment])),
    [transcript],
  );
  const speakerNames = useMemo(
    () =>
      new Map(
        (mappings ?? transcript?.speakers ?? []).map((speaker) => [
          speaker.speaker_id,
          speaker.display_name ??
            (speaker.identity_status === "unknown"
              ? `Unknown speaker (${speaker.speaker_id})`
              : speaker.speaker_id),
        ]),
      ),
    [mappings, transcript],
  );

  if (meetingQuery.isPending) {
    return <p className={styles.message}>Loading meeting…</p>;
  }
  if (meetingQuery.error || !meeting) {
    return (
      <div className={styles.notFound}>
        <h1>Meeting unavailable</h1>
        <p>{errorMessage(meetingQuery.error)}</p>
        <Link href="/meetings">Back to meetings</Link>
      </div>
    );
  }

  if (meeting.status === "queued" || meeting.status === "processing") {
    return (
      <div className={styles.processing}>
        <Link href="/meetings">← Meetings</Link>
        <h1>{meeting.title}</h1>
        <p aria-live="polite">
          {meeting.stage ? stageLabels[meeting.stage] : "Waiting for processing"}
        </p>
        <ol>
          <li data-complete>File received</li>
          <li data-active>Processing securely on your team infrastructure</li>
          <li>Review meeting minutes</li>
          <li>Approve and export PDF</li>
        </ol>
        <p className={styles.processingNote}>
          You can leave this page. Status refreshes automatically.
        </p>
      </div>
    );
  }

  if (meeting.status === "failed") {
    return (
      <div className={styles.processing}>
        <Link href="/meetings">← Meetings</Link>
        <h1>{meeting.title}</h1>
        <p role="alert">{meeting.failure?.message ?? "Processing failed."}</p>
        <button
          disabled={busy || !meeting.source_available}
          onClick={async () => {
            setBusy(true);
            setMessage("");
            try {
              await retryMeeting(meeting.id);
              await queryClient.invalidateQueries({
                queryKey: meetingQueryKeys.detail(meeting.id),
              });
            } catch (error) {
              setMessage(errorMessage(error));
            } finally {
              setBusy(false);
            }
          }}
          type="button"
        >
          {busy ? "Retrying…" : "Retry processing"}
        </button>
        {message ? <p role="alert">{message}</p> : null}
      </div>
    );
  }

  if (results.transcript.isPending || results.insights.isPending) {
    return <p className={styles.message}>Loading the saved results…</p>;
  }
  if (!transcript || !insights || results.transcript.error || results.insights.error) {
    return <p className={styles.message} role="alert">The saved results could not be loaded.</p>;
  }
  const loadedMeeting = meeting;
  const loadedInsights = insights;

  async function refreshAll() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: meetingQueryKeys.all }),
      queryClient.invalidateQueries({ queryKey: meetingQueryKeys.detail(meetingId) }),
      queryClient.invalidateQueries({ queryKey: meetingQueryKeys.transcript(meetingId) }),
      queryClient.invalidateQueries({ queryKey: meetingQueryKeys.insights(meetingId) }),
    ]);
  }

  async function approve() {
    if (!mappings || mappings.some((speaker) => speaker.identity_status === "unreviewed")) {
      setMessage("Name every detected speaker or mark them as unknown first.");
      setActiveTab("transcript");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const saved = await updateReview(meetingId, {
        base_revision: loadedMeeting.revision,
        speaker_mappings: mappings,
        segment_edits: [],
        summary: loadedInsights.summary,
        action_items: loadedInsights.action_items,
      });
      await approveMeeting(meetingId, saved.revision);
      await refreshAll();
      setMessage("Minutes approved and ready to export.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    setBusy(true);
    setMessage("");
    try {
      const pdf = await downloadMeetingPdf(meetingId);
      const url = URL.createObjectURL(pdf);
      const link = document.createElement("a");
      link.href = url;
      link.download = `meeting-${meetingId}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={styles.detail}>
      <nav className={styles.breadcrumb} aria-label="Breadcrumb">
        <Link href="/meetings">Meetings</Link><span>/</span><span>{meeting.title}</span>
      </nav>
      <header className={styles.titleBar}>
        <div>
          <h1>{meeting.title}</h1>
          <p>{meeting.meeting_date} · {meeting.participants.join(", ") || "No participants"}</p>
        </div>
        <strong data-status={meeting.status}>{meetingStatusLabel(meeting.status)}</strong>
      </header>

      {message ? <p className={styles.message} role="status">{message}</p> : null}

      <div className={styles.tabToolbar}>
        <div aria-label="Meeting content" className={styles.tabs} role="tablist">
          {(["summary", "tasks", "transcript"] as const).map((tab) => (
            <button
              aria-selected={activeTab === tab}
              className={styles.tab}
              key={tab}
              onClick={() => setActiveTab(tab)}
              role="tab"
              type="button"
            >
              {tab === "transcript" ? "Full transcript" : `${tab[0]?.toUpperCase()}${tab.slice(1)}`}
            </button>
          ))}
        </div>
        <button
          className={styles.download}
          disabled={meeting.status !== "approved" || busy}
          onClick={() => void downloadPdf()}
          type="button"
        >
          Download PDF
        </button>
      </div>

      {activeTab === "summary" ? (
        <section className={`${styles.section} ${styles.tabPanel}`} role="tabpanel">
          <div className={styles.sectionHeader}><h2>Summary</h2></div>
          <div className={styles.summaryList}>
            {insights.summary.map((item, index) => (
              <article className={styles.summaryItem} key={item.id}>
                <span className={styles.itemNumber}>{String(index + 1).padStart(2, "0")}</span>
                <div><p>{item.text}</p>{item.evidence.map((evidence) => {
                  const source = segments.get(evidence.segment_id);
                  return source ? <blockquote key={`${item.id}-${evidence.segment_id}`}><span>{timestamp(evidence.start_ms)}</span>{source.text}</blockquote> : null;
                })}</div>
              </article>
            ))}
            {insights.summary.length === 0 ? <p>No summary items were extracted.</p> : null}
          </div>
        </section>
      ) : null}

      {activeTab === "tasks" ? (
        <section className={`${styles.section} ${styles.tabPanel}`} role="tabpanel">
          <div className={styles.sectionHeader}><h2>Tasks</h2></div>
          <div className={styles.liveTaskList}>
            {insights.action_items.map((task) => {
              const evidence = task.evidence[0];
              const source = evidence ? segments.get(evidence.segment_id) : undefined;
              return <article className={styles.liveTask} key={task.id}>
                <h3>{task.text}</h3>
                <dl><div><dt>Assignee</dt><dd>{task.assignee_name ?? (task.assignee_speaker_id ? speakerNames.get(task.assignee_speaker_id) : null) ?? "Needs review"}</dd></div><div><dt>Deadline</dt><dd>{task.due_date ?? task.due_date_text ?? "Needs review"}</dd></div></dl>
                {source && evidence ? <blockquote><span>{timestamp(evidence.start_ms)}</span>{source.text}</blockquote> : null}
              </article>;
            })}
            {insights.action_items.length === 0 ? <p>No tasks were extracted.</p> : null}
          </div>
        </section>
      ) : null}

      {activeTab === "transcript" ? (
        <section className={`${styles.section} ${styles.tabPanel}`} role="tabpanel">
          <div className={styles.sectionHeader}><h2>Full transcript</h2></div>
          {meeting.status === "review_required" ? <div className={styles.speakerReview}>
            <h3>Confirm speakers</h3>
            {(mappings ?? []).map((speaker, index) => <label key={speaker.speaker_id}>{speaker.speaker_id}<select value={speaker.identity_status === "unknown" ? "__unknown__" : speaker.display_name ?? ""} onChange={(event) => {
              const value = event.target.value;
              setMappingOverride((current) => (current ?? transcript.speakers).map((item, itemIndex) => itemIndex === index ? value === "__unknown__" ? { ...item, display_name: null, identity_status: "unknown" } : value ? { ...item, display_name: value, identity_status: "named" } : { ...item, display_name: null, identity_status: "unreviewed" } : item));
            }}><option value="">Needs review</option><option value="__unknown__">Unknown speaker</option>{meeting.participants.map((participant) => <option key={participant} value={participant}>{participant}</option>)}</select></label>)}
          </div> : null}
          <div className={styles.transcript}>{transcript.segments.map((segment) => <div key={segment.id}><header><strong>{speakerNames.get(segment.speaker_id)}</strong><span>{timestamp(segment.start_ms)}</span></header><p>{segment.text}</p></div>)}</div>
        </section>
      ) : null}

      {meeting.status === "review_required" ? <footer className={styles.approvalBar}><div><strong>Human review required</strong><span>Confirm every speaker before publishing the minutes.</span></div><button disabled={busy} onClick={() => void approve()} type="button">{busy ? "Saving…" : "Save and approve"}</button></footer> : null}
    </article>
  );
}
