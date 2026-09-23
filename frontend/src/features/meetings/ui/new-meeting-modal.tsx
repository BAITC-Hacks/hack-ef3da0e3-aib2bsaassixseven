"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";

import styles from "./new-meeting-modal.module.scss";

const maxFileSize = 100 * 1024 * 1024;

type ParticipantField = {
  id: number;
  value: string;
};

function initialParticipantFields(): ParticipantField[] {
  return [{ id: 0, value: "" }];
}

export function NewMeetingModal() {
  const router = useRouter();
  const { closeNewMeeting, createMeeting, isNewMeetingOpen } = useDemoWorkspace();
  const formRef = useRef<HTMLFormElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const nextParticipantId = useRef(1);
  const [error, setError] = useState("");
  const [participantFields, setParticipantFields] = useState(
    initialParticipantFields,
  );

  const resetAndClose = useCallback(() => {
    formRef.current?.reset();
    nextParticipantId.current = 1;
    setParticipantFields(initialParticipantFields());
    setError("");
    closeNewMeeting();
  }, [closeNewMeeting]);

  useEffect(() => {
    if (!isNewMeetingOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    titleRef.current?.focus();

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") resetAndClose();
    };
    window.addEventListener("keydown", closeOnEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [isNewMeetingOpen, resetAndClose]);

  if (!isNewMeetingOpen) return null;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const formData = new FormData(event.currentTarget);
    const fileInput = event.currentTarget.elements.namedItem("recording");
    const file =
      fileInput instanceof HTMLInputElement ? fileInput.files?.[0] : undefined;

    if (!(file instanceof File) || file.size === 0) {
      setError("Choose a meeting audio or video file.");
      return;
    }
    if (file.size > maxFileSize) {
      setError("The file exceeds the 100 MiB limit.");
      return;
    }

    const participantNames = formData
      .getAll("participants")
      .map(String)
      .map((name) => name.trim())
      .filter(Boolean);
    if (participantNames.length === 0) {
      setError("Add at least one participant username.");
      return;
    }

    const id = createMeeting({
      title: String(formData.get("title") ?? "").trim(),
      recordedAt: String(formData.get("recordedAt") ?? ""),
      participantNames,
      audioFileName: file.name,
    });

    formRef.current?.reset();
    nextParticipantId.current = 1;
    setParticipantFields(initialParticipantFields());
    closeNewMeeting();
    router.push(`/meetings/${id}`);
  }

  function addParticipantField() {
    const id = nextParticipantId.current;
    nextParticipantId.current += 1;
    setParticipantFields((current) => [...current, { id, value: "" }]);
  }

  function removeParticipantField(id: number) {
    setParticipantFields((current) =>
      current.filter((participant) => participant.id !== id),
    );
  }

  return (
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) resetAndClose();
      }}
    >
      <section
        aria-labelledby="new-meeting-title"
        aria-modal="true"
        className={styles.modal}
        role="dialog"
      >
        <header className={styles.header}>
          <div>
            <h2 id="new-meeting-title">New meeting</h2>
            <p>Add a recording and the context needed to review it.</p>
          </div>
          <button
            aria-label="Close dialog"
            className={styles.close}
            onClick={resetAndClose}
            type="button"
          >
            ×
          </button>
        </header>

        <form className={styles.form} onSubmit={handleSubmit} ref={formRef}>
          <div className={styles.columns}>
            <label className={styles.fullWidth}>
              Meeting title
              <input
                name="title"
                placeholder="Weekly product sync"
                ref={titleRef}
                required
                type="text"
              />
            </label>
            <label className={styles.dateField}>
              Date and time
              <input name="recordedAt" required type="datetime-local" />
            </label>
            <fieldset className={styles.participants}>
              <legend>Participants</legend>
              <p>Add each person by username.</p>
              <div className={styles.participantList}>
                {participantFields.map((participant, index) => (
                  <div className={styles.participantRow} key={participant.id}>
                    <label
                      className={styles.visuallyHidden}
                      htmlFor={`participant-${participant.id}`}
                    >
                      Participant username {index + 1}
                    </label>
                    <div className={styles.usernameInput}>
                      <span aria-hidden="true">@</span>
                      <input
                        autoComplete="off"
                        id={`participant-${participant.id}`}
                        name="participants"
                        onChange={(event) =>
                          setParticipantFields((current) =>
                            current.map((item) =>
                              item.id === participant.id
                                ? { ...item, value: event.target.value }
                                : item,
                            ),
                          )
                        }
                        placeholder="username"
                        required
                        type="text"
                        value={participant.value}
                      />
                    </div>
                    <div className={styles.participantControls}>
                      {participantFields.length > 1 ? (
                        <button
                          aria-label={`Remove participant ${index + 1}`}
                          className={styles.participantControl}
                          onClick={() => removeParticipantField(participant.id)}
                          type="button"
                        >
                          <span aria-hidden="true">−</span>
                        </button>
                      ) : null}
                      {index === participantFields.length - 1 ? (
                        <button
                          aria-label="Add another participant"
                          className={styles.participantControl}
                          onClick={addParticipantField}
                          type="button"
                        >
                          <span aria-hidden="true">+</span>
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </fieldset>
            <label className={styles.fullWidth}>
              Meeting recording
              <input
                accept=".wav,.mp3,.m4a,.ogg,.webm,audio/*,video/webm"
                name="recording"
                required
                type="file"
              />
              <span>WAV, MP3, M4A, OGG or WebM · up to 100 MiB</span>
            </label>
          </div>

          <label className={styles.consent}>
            <input name="consent" required type="checkbox" />
            Participants have been informed about the recording and automated
            transcription.
          </label>

          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}

          <footer className={styles.footer}>
            <button onClick={resetAndClose} type="button">
              Cancel
            </button>
            <button className={styles.primary} type="submit">
              Start processing
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
