"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useMemo, useRef, useState } from "react";

import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";
import {
  formatMeetingDate,
  meetingStatusLabel,
} from "@/features/demo-workspace/lib/format";
import type {
  DemoAssignment,
  DemoMeeting,
} from "@/features/demo-workspace/model/demo-data";
import { LiveMeetingDetailView } from "./live-meeting-detail-view";

import styles from "./meeting-detail-view.module.scss";

const meetingTabs = [
  { id: "summary", label: "Summary" },
  { id: "tasks", label: "Tasks" },
  { id: "transcript", label: "Full transcript" },
] as const;

type MeetingTab = (typeof meetingTabs)[number]["id"];

function emptyAssignment(): DemoAssignment {
  return {
    id: crypto.randomUUID(),
    title: "",
    assignee: null,
    dueDate: null,
    status: "open",
    evidence: "Added manually",
    time: "—",
  };
}

export function MeetingDetailView({ meetingId }: { meetingId: string }) {
  const { isDemo } = useDemoWorkspace();
  return isDemo ? (
    <DemoMeetingDetailView meetingId={meetingId} />
  ) : (
    <LiveMeetingDetailView meetingId={meetingId} />
  );
}

function DemoMeetingDetailView({ meetingId }: { meetingId: string }) {
  const router = useRouter();
  const {
    approveMeeting,
    deleteMeeting,
    meetings,
    saveReview,
  } = useDemoWorkspace();
  const meeting = meetings.find((item) => item.id === meetingId);
  const tabIdPrefix = useId();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [draftOverride, setDraft] = useState<DemoMeeting | null>(null);
  const [editingOverride, setIsEditing] = useState<boolean | null>(null);
  const [message, setMessage] = useState("");
  const [activeTab, setActiveTab] = useState<MeetingTab>("summary");
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
        <h1>Meeting not found</h1>
        <p>It may have been deleted from this demo session.</p>
        <Link href="/meetings">Back to meetings</Link>
      </div>
    );
  }

  if (meeting.status === "processing" || meeting.status === "queued") {
    return (
      <div className={styles.processing}>
        <Link href="/meetings">← Meetings</Link>
        <h1>{meeting.title}</h1>
        <p aria-live="polite">
          {meeting.processingStage || "Waiting to process this recording"}
        </p>
        <ol>
          <li data-complete>File received</li>
          <li data-active>Processing the recording locally</li>
          <li>Review meeting minutes</li>
          <li>Approve and export PDF</li>
        </ol>
        <p className={styles.processingNote}>
          You can leave this page. Processing will continue in the background.
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
    setMessage("Changes saved. The minutes need approval.");
  }

  function approveDraft() {
    saveDraft();
    approveMeeting(meetingId);
    setIsEditing(false);
    setMessage("Minutes approved and ready to export.");
  }

  async function shareMeeting() {
    if (!draft) return;
    const url = window.location.href;
    if (navigator.share) {
      await navigator.share({ title: draft.title, url }).catch(() => undefined);
      return;
    }
    await navigator.clipboard.writeText(url);
    setMessage("Link copied.");
  }

  function activateTab(index: number) {
    const tab = meetingTabs[index];
    if (!tab) return;
    setActiveTab(tab.id);
    tabRefs.current[index]?.focus();
  }

  function handleTabKeyDown(
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) {
    let nextIndex: number | null = null;

    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % meetingTabs.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + meetingTabs.length) % meetingTabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = meetingTabs.length - 1;
    }

    if (nextIndex === null) return;
    event.preventDefault();
    activateTab(nextIndex);
  }

  function panelClassName(tab: MeetingTab) {
    return activeTab === tab
      ? `${styles.section} ${styles.tabPanel}`
      : `${styles.section} ${styles.tabPanel} ${styles.tabPanelHidden}`;
  }

  return (
    <article className={styles.detail}>
      <nav className={styles.breadcrumb} aria-label="Breadcrumb">
        <Link href="/meetings">Meetings</Link>
        <span>/</span>
        <span>{draft.title}</span>
      </nav>

      <header className={styles.titleBar}>
        <div>
          {isEditing ? (
            <input
              aria-label="Meeting title"
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
            {draft.participantNames.length}{" "}
            {draft.participantNames.length === 1 ? "participant" : "participants"}
          </p>
        </div>
        <strong data-status={meeting.status}>
          {meetingStatusLabel(meeting.status)}
        </strong>
      </header>

      <div className={styles.actions}>
        {meeting.status === "approved" && !isEditing ? (
          <button onClick={() => setIsEditing(true)} type="button">
            Edit
          </button>
        ) : null}
        {isEditing ? (
          <button onClick={saveDraft} type="button">
            Save
          </button>
        ) : null}
        <button onClick={shareMeeting} type="button">
          Share
        </button>
        <button
          className={styles.delete}
          onClick={() => {
            if (window.confirm(`Delete “${meeting.title}”?`)) {
              deleteMeeting(meeting.id);
              router.push("/meetings");
            }
          }}
          type="button"
        >
          Delete
        </button>
      </div>

      {message ? (
        <p aria-live="polite" className={styles.message}>
          {message}
        </p>
      ) : null}

      {missingFields > 0 ? (
        <p className={styles.warning} role="status">
          {missingFields} assignment{missingFields === 1 ? "" : "s"}{" "}
          {missingFields === 1 ? "has" : "have"} a missing assignee, deadline
          or title. This is allowed, but review the fields before approval.
        </p>
      ) : null}

      <div className={styles.tabToolbar}>
        <div aria-label="Meeting content" className={styles.tabs} role="tablist">
          {meetingTabs.map((tab, index) => {
            const isActive = activeTab === tab.id;
            const tabId = `${tabIdPrefix}-${tab.id}-tab`;
            const panelId = `${tabIdPrefix}-${tab.id}-panel`;

            return (
              <button
                aria-controls={panelId}
                aria-selected={isActive}
                className={styles.tab}
                id={tabId}
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
                ref={(element) => {
                  tabRefs.current[index] = element;
                }}
                role="tab"
                tabIndex={isActive ? 0 : -1}
                type="button"
              >
                {tab.label}
              </button>
            );
          })}
        </div>
        <button
          className={styles.download}
          disabled={meeting.status !== "approved" || isEditing}
          onClick={() => window.print()}
          title={
            meeting.status === "approved" && !isEditing
              ? "Download the approved minutes as PDF"
              : "Approve the saved minutes before downloading"
          }
          type="button"
        >
          Download PDF
        </button>
      </div>

      <section
        aria-hidden={activeTab !== "summary"}
        aria-labelledby={`${tabIdPrefix}-summary-tab`}
        className={panelClassName("summary")}
        id={`${tabIdPrefix}-summary-panel`}
        role="tabpanel"
        tabIndex={activeTab === "summary" ? 0 : -1}
      >
        <h2>Summary</h2>
        {isEditing ? (
          <textarea
            aria-label="Meeting summary"
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

      <section
        aria-hidden={activeTab !== "tasks"}
        aria-labelledby={`${tabIdPrefix}-tasks-tab`}
        className={panelClassName("tasks")}
        id={`${tabIdPrefix}-tasks-panel`}
        role="tabpanel"
        tabIndex={activeTab === "tasks" ? 0 : -1}
      >
        <div className={styles.sectionHeader}>
          <h2>Tasks</h2>
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
              + Add task
            </button>
          ) : null}
        </div>
        <div className={styles.assignmentList}>
          {draft.assignments.map((task, index) => (
            <div className={styles.assignment} key={task.id}>
              {isEditing ? (
                <>
                  <label className={styles.assignmentTitle}>
                    Task
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
                    Assignee
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
                    Deadline
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
                    Delete
                  </button>
                </>
              ) : (
                <>
                  <strong>{task.title}</strong>
                  <span>{task.assignee || "Assignee not set"}</span>
                  <span>{task.dueDate || "Deadline not set"}</span>
                </>
              )}
              <p>
                <span>{task.time}</span> “{task.evidence}”
              </p>
            </div>
          ))}
        </div>
      </section>

      <section
        aria-hidden={activeTab !== "transcript"}
        aria-labelledby={`${tabIdPrefix}-transcript-tab`}
        className={panelClassName("transcript")}
        id={`${tabIdPrefix}-transcript-panel`}
        role="tabpanel"
        tabIndex={activeTab === "transcript" ? 0 : -1}
      >
        <h2>Full transcript</h2>
        <div className={styles.transcript}>
          {draft.transcript.map((segment, index) => (
            <div key={segment.id}>
              <header>
                <strong>{segment.speaker}</strong>
                <span>{segment.time}</span>
              </header>
              {isEditing ? (
                <textarea
                  aria-label={`Transcript segment from ${segment.speaker} at ${segment.time}`}
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
            <strong>Review the result before approval</strong>
            <span>Any later edit will require approval again.</span>
          </div>
          <button onClick={approveDraft} type="button">
            Approve minutes
          </button>
        </footer>
      ) : null}
    </article>
  );
}
