"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useId, useMemo, useRef, useState } from "react";

import { meetingStatusLabel } from "@/features/demo-workspace/lib/format";
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
import type {
  ActionItem,
  Insights,
  SummaryItem,
  Transcript,
  TranscriptSpeaker,
} from "@/features/meetings/api/schemas";

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

type Tab = "summary" | "tasks" | "transcript";
const tabs: Tab[] = ["summary", "tasks", "transcript"];
type ReviewDraft = {
  speakers: TranscriptSpeaker[];
  segments: Transcript["segments"];
  summary: SummaryItem[];
  tasks: ActionItem[];
};

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

function initialDraft(transcript: Transcript, insights: Insights): ReviewDraft {
  return {
    speakers: transcript.speakers,
    segments: transcript.segments,
    summary: insights.summary,
    tasks: insights.action_items,
  };
}

function evidenceFor(segment: Transcript["segments"][number]) {
  return [{
    segment_id: segment.id,
    start_ms: segment.start_ms,
    end_ms: segment.end_ms,
  }];
}

function replacePrimaryEvidence(
  existing: SummaryItem["evidence"],
  segment: Transcript["segments"][number] | undefined,
): SummaryItem["evidence"] {
  return segment ? [...evidenceFor(segment), ...existing.slice(1)] : existing.slice(1);
}

export function LiveMeetingDetailView({ meetingId }: { meetingId: string }) {
  const queryClient = useQueryClient();
  const meetingQuery = useMeetingQuery(meetingId);
  const meeting = meetingQuery.data;
  const ready = meeting?.status === "review_required" || meeting?.status === "approved";
  const results = useMeetingResultsQuery(meetingId, ready);
  const transcript = results.transcript.data;
  const insights = results.insights.data;
  const [activeTab, setActiveTab] = useState<Tab>("summary");
  const [draftState, setDraftState] = useState<{ key: string; value: ReviewDraft } | null>(null);
  const [editingApproved, setEditingApproved] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const tabIdPrefix = useId();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const revisionKey = `${meetingId}:${meeting?.revision ?? -1}`;
  const draft = transcript && insights
    ? draftState?.key === revisionKey
      ? draftState.value
      : initialDraft(transcript, insights)
    : null;
  const isEditing = meeting?.status === "review_required" || editingApproved;

  const segments = useMemo(
    () => new Map(draft?.segments.map((segment) => [segment.id, segment])),
    [draft?.segments],
  );
  const speakerNames = useMemo(
    () => new Map((draft?.speakers ?? []).map((speaker) => [
      speaker.speaker_id,
      speaker.display_name ??
        (speaker.identity_status === "unknown"
          ? `Unknown speaker (${speaker.speaker_id})`
          : speaker.speaker_id),
    ])),
    [draft?.speakers],
  );

  function changeDraft(change: (current: ReviewDraft) => ReviewDraft) {
    if (!draft) return;
    setDraftState({ key: revisionKey, value: change(draft) });
    setMessage("");
  }

  function changeSummary(id: string, patch: Partial<SummaryItem>) {
    changeDraft((current) => ({
      ...current,
      summary: current.summary.map((item) => item.id === id ? { ...item, ...patch } : item),
    }));
  }

  function changeTask(id: string, patch: Partial<ActionItem>) {
    changeDraft((current) => ({
      ...current,
      tasks: current.tasks.map((item) => item.id === id ? { ...item, ...patch } : item),
    }));
  }

  function handleTabKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabs.length - 1;
    if (nextIndex === null) return;
    const nextTab = tabs[nextIndex];
    if (!nextTab) return;
    event.preventDefault();
    setActiveTab(nextTab);
    tabRefs.current[nextIndex]?.focus();
  }

  async function refreshAll() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: meetingQueryKeys.all }),
      queryClient.invalidateQueries({ queryKey: meetingQueryKeys.detail(meetingId) }),
      queryClient.invalidateQueries({ queryKey: meetingQueryKeys.transcript(meetingId) }),
      queryClient.invalidateQueries({ queryKey: meetingQueryKeys.insights(meetingId) }),
    ]);
  }

  function validateDraft(current: ReviewDraft): string | null {
    if (current.speakers.some((speaker) => speaker.identity_status === "named" && !speaker.display_name?.trim())) {
      return "Enter a name for each named speaker.";
    }
    if (current.segments.some((segment) => !segment.text.trim())) {
      return "Transcript segments cannot be empty.";
    }
    if (current.summary.some((item) => !item.text.trim() || item.evidence.length === 0)) {
      return "Every summary item needs text and a source segment.";
    }
    if (current.tasks.some((item) => !item.text.trim() || item.evidence.length === 0 || (item.assignee_name !== null && !item.assignee_name.trim()))) {
      return "Every task needs text and a source segment. Enter a name or leave the assignee unknown.";
    }
    return null;
  }

  async function save(): Promise<number | null> {
    if (!meeting || !draft) return null;
    const problem = validateDraft(draft);
    if (problem) {
      setMessage(problem);
      return null;
    }
    setBusy(true);
    setMessage("");
    try {
      // The backend overlays the original model result on every revision. Sending
      // every displayed segment preserves edits saved in earlier revisions.
      const saved = await updateReview(meetingId, {
        base_revision: meeting.revision,
        speaker_mappings: draft.speakers,
        segment_edits: draft.segments.map((segment) => ({
          segment_id: segment.id,
          text: segment.text,
          speaker_id: segment.speaker_id,
        })),
        summary: draft.summary,
        action_items: draft.tasks.map((task) => ({
          ...task,
          assignee_name: task.assignee_name?.trim() ?? null,
        })),
      });
      await refreshAll();
      setMessage("Changes saved. Review the current revision before approval.");
      return saved.revision;
    } catch (error) {
      setMessage(errorMessage(error));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!meeting || !draft) return;
    if (draft.speakers.some((speaker) => speaker.identity_status === "unreviewed")) {
      setMessage("Name every detected speaker or mark them as unknown first.");
      setActiveTab("transcript");
      return;
    }
    if (draftState?.key === revisionKey) {
      setMessage("Save the review, then approve the saved revision.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await approveMeeting(meetingId, meeting.revision);
      await refreshAll();
      setEditingApproved(false);
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
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  if (meetingQuery.isPending) return <p className={styles.message}>Loading meeting…</p>;
  if (meetingQuery.error || !meeting) {
    return <div className={styles.notFound}>
      <h1>Meeting unavailable</h1><p>{errorMessage(meetingQuery.error)}</p>
      <Link href="/meetings">Back to meetings</Link>
    </div>;
  }

  if (meeting.status === "queued" || meeting.status === "processing") {
    return <div className={styles.processing}>
      <Link href="/meetings">← Meetings</Link><h1>{meeting.title}</h1>
      <p aria-live="polite">{meeting.stage ? stageLabels[meeting.stage] : "Waiting for processing"}</p>
      <ol><li data-complete>File received</li><li data-active>Processing securely on your team infrastructure</li><li>Review meeting minutes</li><li>Approve and export PDF</li></ol>
      <p className={styles.processingNote}>You can leave this page. Status refreshes automatically.</p>
    </div>;
  }

  if (meeting.status === "failed") {
    return <div className={styles.processing}>
      <Link href="/meetings">← Meetings</Link><h1>{meeting.title}</h1>
      <p role="alert">{meeting.failure?.message ?? "Processing failed."}</p>
      <button disabled={busy || !meeting.source_available} onClick={async () => {
        setBusy(true);
        setMessage("");
        try {
          await retryMeeting(meeting.id);
          await queryClient.invalidateQueries({ queryKey: meetingQueryKeys.detail(meeting.id) });
        } catch (error) {
          setMessage(errorMessage(error));
        } finally {
          setBusy(false);
        }
      }} type="button">{busy ? "Retrying…" : "Retry processing"}</button>
      {!meeting.source_available ? <p>The temporary recording is unavailable. Upload it again as a new meeting.</p> : null}
      {message ? <p role="alert">{message}</p> : null}
    </div>;
  }

  if (results.transcript.error || results.insights.error) {
    return <p className={styles.message} role="alert">The saved results could not be loaded.</p>;
  }
  if (results.transcript.isPending || results.insights.isPending ||
      transcript?.revision !== meeting.revision || insights?.revision !== meeting.revision || !draft) {
    return <p className={styles.message}>Loading the saved results…</p>;
  }

  const unsaved = draftState?.key === revisionKey;
  const invalid = validateDraft(draft);

  return <article className={styles.detail}>
    <nav className={styles.breadcrumb} aria-label="Breadcrumb"><Link href="/meetings">Meetings</Link><span>/</span><span>{meeting.title}</span></nav>
    <header className={styles.titleBar}><div><h1>{meeting.title}</h1><p>{meeting.meeting_date} · {meeting.participants.join(", ") || "No participants"}</p></div><strong data-status={meeting.status}>{meetingStatusLabel(meeting.status)}</strong></header>
    {meeting.status === "approved" && !isEditing ? <div className={styles.actions}><button onClick={() => setEditingApproved(true)} type="button">Edit minutes</button></div> : null}
    {message ? <p className={styles.message} role="status">{message}</p> : null}
    {isEditing && invalid ? <p className={styles.warning} role="status">{invalid}</p> : null}
    <div className={styles.tabToolbar}>
      <div aria-label="Meeting content" className={styles.tabs} role="tablist">
        {tabs.map((tab, index) => <button aria-controls={`${tabIdPrefix}-${tab}-panel`} aria-selected={activeTab === tab} className={styles.tab} id={`${tabIdPrefix}-${tab}-tab`} key={tab} onClick={() => setActiveTab(tab)} onKeyDown={(event) => handleTabKeyDown(event, index)} ref={(element) => { tabRefs.current[index] = element; }} role="tab" tabIndex={activeTab === tab ? 0 : -1} type="button">{tab === "transcript" ? "Full transcript" : `${tab[0]?.toUpperCase()}${tab.slice(1)}`}</button>)}
      </div>
      <button className={styles.download} disabled={meeting.status !== "approved" || isEditing || busy} onClick={() => void downloadPdf()} type="button">Download PDF</button>
    </div>

    <section aria-labelledby={`${tabIdPrefix}-summary-tab`} className={`${styles.section} ${styles.tabPanel}`} hidden={activeTab !== "summary"} id={`${tabIdPrefix}-summary-panel`} role="tabpanel" tabIndex={activeTab === "summary" ? 0 : -1}>
      <div className={styles.sectionHeader}><h2>Summary</h2>{isEditing ? <button disabled={busy} onClick={() => changeDraft((current) => ({ ...current, summary: [...current.summary, { id: crypto.randomUUID(), text: "", evidence: [] }] }))} type="button">+ Add summary item</button> : null}</div>
      <div className={styles.summaryList}>{draft.summary.map((item, index) => <article className={styles.summaryItem} key={item.id}>
        <span className={styles.itemNumber}>{String(index + 1).padStart(2, "0")}</span>
        <div>
          {isEditing ? <label className={styles.liveField}>Summary item<textarea aria-label={`Summary item ${index + 1}`} disabled={busy} onChange={(event) => changeSummary(item.id, { text: event.target.value })} rows={3} value={item.text} /></label> : <p>{item.text}</p>}
          {isEditing ? <label className={styles.liveField}>Primary source segment<select disabled={busy} onChange={(event) => changeSummary(item.id, { evidence: replacePrimaryEvidence(item.evidence, segments.get(event.target.value)) })} value={item.evidence[0]?.segment_id ?? ""}><option value="">Choose a transcript segment</option>{draft.segments.map((segment) => <option key={segment.id} value={segment.id}>{timestamp(segment.start_ms)} · {segment.text.slice(0, 90)}</option>)}</select></label> : null}
          {item.evidence.map((evidence) => { const source = segments.get(evidence.segment_id); return source ? <blockquote key={`${item.id}-${evidence.segment_id}`}><span>{timestamp(evidence.start_ms)}</span>{source.text}</blockquote> : null; })}
          {isEditing ? <button className={styles.liveRemove} disabled={busy} onClick={() => changeDraft((current) => ({ ...current, summary: current.summary.filter((entry) => entry.id !== item.id) }))} type="button">Delete item</button> : null}
        </div>
      </article>)}{draft.summary.length === 0 ? <p>No summary items were extracted.</p> : null}</div>
    </section>

    <section aria-labelledby={`${tabIdPrefix}-tasks-tab`} className={`${styles.section} ${styles.tabPanel}`} hidden={activeTab !== "tasks"} id={`${tabIdPrefix}-tasks-panel`} role="tabpanel" tabIndex={activeTab === "tasks" ? 0 : -1}>
      <div className={styles.sectionHeader}><h2>Tasks</h2>{isEditing ? <button disabled={busy} onClick={() => changeDraft((current) => ({ ...current, tasks: [...current.tasks, { id: crypto.randomUUID(), text: "", evidence: [], assignee_speaker_id: null, assignee_name: null, due_date: null, due_date_text: null }] }))} type="button">+ Add task</button> : null}</div>
      <div className={styles.liveTaskList}>{draft.tasks.map((task, index) => {
        return <article className={styles.liveTask} key={task.id}>
          {isEditing ? <div className={styles.liveEditGrid}>
            <label className={styles.liveField}>Task<textarea aria-label={`Task ${index + 1}`} disabled={busy} onChange={(event) => changeTask(task.id, { text: event.target.value })} rows={2} value={task.text} /></label>
            <label className={styles.liveField}>Assignee<select disabled={busy} onChange={(event) => { const value = event.target.value; changeTask(task.id, { assignee_speaker_id: value.startsWith("speaker_") ? value : null, assignee_name: value === "__external__" ? "" : null }); }} value={task.assignee_speaker_id ?? (task.assignee_name !== null ? "__external__" : "")}><option value="">Unknown / not assigned</option>{draft.speakers.map((speaker) => <option key={speaker.speaker_id} value={speaker.speaker_id}>{speakerNames.get(speaker.speaker_id)}</option>)}<option value="__external__">Other person</option></select></label>
            {task.assignee_name !== null ? <label className={styles.liveField}>Assignee name<input disabled={busy} onChange={(event) => changeTask(task.id, { assignee_name: event.target.value })} value={task.assignee_name} /></label> : null}
            <label className={styles.liveField}>Deadline<input disabled={busy} onChange={(event) => changeTask(task.id, { due_date: event.target.value || null })} type="date" value={task.due_date ?? ""} /></label>
            {task.due_date_text ? <p className={styles.spokenDeadline}>Spoken deadline: {task.due_date_text}</p> : null}
            <label className={styles.liveField}>Primary source segment<select disabled={busy} onChange={(event) => changeTask(task.id, { evidence: replacePrimaryEvidence(task.evidence, segments.get(event.target.value)) })} value={task.evidence[0]?.segment_id ?? ""}><option value="">Choose a transcript segment</option>{draft.segments.map((segment) => <option key={segment.id} value={segment.id}>{timestamp(segment.start_ms)} · {segment.text.slice(0, 90)}</option>)}</select></label>
            <button className={styles.liveRemove} disabled={busy} onClick={() => changeDraft((current) => ({ ...current, tasks: current.tasks.filter((entry) => entry.id !== task.id) }))} type="button">Delete task</button>
          </div> : <><h3>{task.text}</h3><dl><div><dt>Assignee</dt><dd>{task.assignee_name ?? (task.assignee_speaker_id ? speakerNames.get(task.assignee_speaker_id) : null) ?? "Needs review"}</dd></div><div><dt>Deadline</dt><dd>{task.due_date ?? task.due_date_text ?? "Needs review"}</dd></div></dl></>}
          {task.evidence.map((evidence) => { const source = segments.get(evidence.segment_id); return source ? <blockquote key={`${evidence.segment_id}-${evidence.start_ms}`}><span>{timestamp(evidence.start_ms)}</span>{source.text}</blockquote> : null; })}
        </article>;
      })}{draft.tasks.length === 0 ? <p>No tasks were extracted.</p> : null}</div>
    </section>

    <section aria-labelledby={`${tabIdPrefix}-transcript-tab`} className={`${styles.section} ${styles.tabPanel}`} hidden={activeTab !== "transcript"} id={`${tabIdPrefix}-transcript-panel`} role="tabpanel" tabIndex={activeTab === "transcript" ? 0 : -1}>
      <div className={styles.sectionHeader}><h2>Full transcript</h2></div>
      {isEditing ? <div className={styles.speakerReview}><h3>Confirm speakers</h3>{draft.speakers.map((speaker) => <div className={styles.speakerRow} key={speaker.speaker_id}>
        <span>{speaker.speaker_id}</span>
        <label className={styles.liveField}>Identity<select disabled={busy} onChange={(event) => { const value = event.target.value; changeDraft((current) => ({ ...current, speakers: current.speakers.map((item) => item.speaker_id === speaker.speaker_id ? { ...item, identity_status: value as TranscriptSpeaker["identity_status"], display_name: value === "named" ? (item.display_name ?? "") : null } : item) })); }} value={speaker.identity_status}><option value="unreviewed">Needs review</option><option value="unknown">Unknown speaker</option><option value="named">Named speaker</option></select></label>
        {speaker.identity_status === "named" ? <label className={styles.liveField}>Name<input disabled={busy} onChange={(event) => changeDraft((current) => ({ ...current, speakers: current.speakers.map((item) => item.speaker_id === speaker.speaker_id ? { ...item, display_name: event.target.value } : item) }))} value={speaker.display_name ?? ""} /></label> : null}
      </div>)}</div> : null}
      <div className={styles.transcript}>{draft.segments.map((segment) => <div key={segment.id}><header><strong>{speakerNames.get(segment.speaker_id)}</strong><span>{timestamp(segment.start_ms)}</span></header>{isEditing ? <div className={styles.liveTranscriptEdit}><label className={styles.liveField}>Speaker<select disabled={busy} onChange={(event) => changeDraft((current) => ({ ...current, segments: current.segments.map((item) => item.id === segment.id ? { ...item, speaker_id: event.target.value } : item) }))} value={segment.speaker_id}>{draft.speakers.map((speaker) => <option key={speaker.speaker_id} value={speaker.speaker_id}>{speakerNames.get(speaker.speaker_id)}</option>)}</select></label><label className={styles.liveField}>Transcript text<textarea disabled={busy} onChange={(event) => changeDraft((current) => ({ ...current, segments: current.segments.map((item) => item.id === segment.id ? { ...item, text: event.target.value } : item) }))} rows={3} value={segment.text} /></label></div> : <p>{segment.text}</p>}</div>)}</div>
    </section>

    {isEditing ? <footer className={styles.approvalBar}><div><strong>Human review required</strong><span>Save corrections, confirm every speaker, then approve this revision.</span></div><div className={styles.liveApprovalActions}><button disabled={busy} onClick={() => { setDraftState(null); setEditingApproved(false); setMessage(""); }} type="button">Discard unsaved changes</button><button disabled={busy || !unsaved || Boolean(invalid)} onClick={() => void save()} type="button">{busy ? "Saving…" : "Save changes"}</button><button disabled={busy || unsaved || meeting.status !== "review_required" || draft.speakers.some((speaker) => speaker.identity_status === "unreviewed")} onClick={() => void approve()} type="button">Approve saved revision</button></div></footer> : null}
  </article>;
}
