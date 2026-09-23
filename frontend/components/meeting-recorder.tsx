"use client";

import { useEffect, useRef, useState } from "react";

import {
  createBrowserRecording,
  MAX_RECORDING_BYTES,
  RecordingError,
  type RecordingResult,
  type StopReason,
} from "@/lib/browser-recording";
import {
  createMeetingFromAudio,
  type CreatedMeeting,
  type MeetingUploadMetadata,
} from "@/lib/meetings-api";

type RecordingState = "idle" | "requesting" | "recording" | "stopping" | "preview" | "uploading" | "error";
type Recorder = ReturnType<typeof createBrowserRecording>;

export function MeetingRecorder({
  metadata,
  getAccessToken,
  onCreated,
}: {
  metadata: Omit<MeetingUploadMetadata, "recording_notice_confirmed">;
  getAccessToken: () => Promise<string | null>;
  onCreated?: (meeting: CreatedMeeting) => void;
}) {
  const [state, setState] = useState<RecordingState>("idle");
  const [noticeConfirmed, setNoticeConfirmed] = useState(false);
  const [result, setResult] = useState<RecordingResult | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [created, setCreated] = useState<CreatedMeeting | null>(null);
  const recorderRef = useRef<Recorder | null>(null);
  const previewRef = useRef<string | null>(null);
  const previewBlobRef = useRef<Blob | null>(null);
  const mountedRef = useRef(true);
  const recordingGenerationRef = useRef(0);
  const sessionActiveRef = useRef(false);
  const uploadingRef = useRef(false);

  useEffect(() => {
    if (state !== "recording") return;
    const startedAt = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [state]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      recordingGenerationRef.current += 1;
      void recorderRef.current?.disposeRecording();
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
      previewRef.current = null;
    };
  }, []);

  function clearPreview() {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = null;
    previewBlobRef.current = null;
    setPreviewUrl(null);
    setResult(null);
  }

  function showPreview(next: RecordingResult, reason: StopReason) {
    if (!mountedRef.current) return;
    if (previewBlobRef.current === next.blob) return;
    clearPreview();
    const url = URL.createObjectURL(next.blob);
    previewRef.current = url;
    previewBlobRef.current = next.blob;
    setPreviewUrl(url);
    setResult(next);
    setState("preview");
    if (next.sizeBytes > MAX_RECORDING_BYTES) {
      setMessage("Запись превышает 100 МиБ. Удалите её и запишите встречу заново");
    } else if (reason === "size_limit") {
      setMessage("Запись остановлена у лимита размера. Прослушайте файл перед отправкой");
    } else if (reason === "display_ended" || reason === "audio_ended") {
      setMessage("Демонстрация или звук остановлены. Прослушайте запись перед отправкой");
    } else if (reason === "encoding_error") {
      setMessage("Запись прервана ошибкой кодирования. Проверьте, воспроизводится ли файл");
    } else {
      setMessage(null);
    }
  }

  async function start() {
    if ((state !== "idle" && state !== "error") || sessionActiveRef.current) return;
    sessionActiveRef.current = true;
    const generation = ++recordingGenerationRef.current;
    clearPreview();
    setMessage(null);
    setCreated(null);
    setNoticeConfirmed(false);
    uploadingRef.current = false;
    setSeconds(0);
    setState("requesting");
    const recorder = createBrowserRecording(
      (next, reason) => {
        if (recordingGenerationRef.current === generation) showPreview(next, reason);
      },
      (error) => {
        if (recordingGenerationRef.current !== generation || recorderRef.current !== recorder) return;
        void recorder.disposeRecording().catch(() => {}).then(() => {
          if (recordingGenerationRef.current !== generation || recorderRef.current !== recorder) return;
          recorderRef.current = null;
          sessionActiveRef.current = false;
          if (!mountedRef.current) return;
          setMessage(error instanceof Error ? error.message : "Не удалось завершить запись. Попробуйте снова");
          setState("error");
        });
      },
    );
    recorderRef.current = recorder;
    try {
      await recorder.startRecording();
      if (mountedRef.current && recorderRef.current === recorder && !previewBlobRef.current) setState("recording");
    } catch (error) {
      await recorder.disposeRecording().catch(() => {});
      if (recorderRef.current === recorder) recorderRef.current = null;
      sessionActiveRef.current = false;
      if (mountedRef.current && recordingGenerationRef.current === generation) {
        setMessage(error instanceof RecordingError ? error.message : "Не удалось начать запись. Проверьте разрешения и попробуйте снова");
        setState("error");
      }
    }
  }

  async function stop() {
    if (state !== "recording" || !recorderRef.current) return;
    const recorder = recorderRef.current;
    const generation = recordingGenerationRef.current;
    setState("stopping");
    try {
      const next = await recorder.stopRecording();
      if (recordingGenerationRef.current === generation) showPreview(next, "manual");
    } catch (error) {
      await recorder.disposeRecording().catch(() => {});
      if (recorderRef.current === recorder) recorderRef.current = null;
      sessionActiveRef.current = false;
      if (mountedRef.current && recordingGenerationRef.current === generation) {
        setMessage(error instanceof Error ? error.message : "Не удалось завершить запись. Попробуйте снова");
        setState("error");
      }
    }
  }

  async function remove() {
    recordingGenerationRef.current += 1;
    sessionActiveRef.current = false;
    clearPreview();
    setMessage(null);
    setCreated(null);
    setNoticeConfirmed(false);
    const recorder = recorderRef.current;
    recorderRef.current = null;
    setState("idle");
    await recorder?.disposeRecording();
  }

  async function upload() {
    if (state !== "preview" || !result || !noticeConfirmed || created || uploadingRef.current) return;
    if (result.sizeBytes > MAX_RECORDING_BYTES) return;
    uploadingRef.current = true;
    setState("uploading");
    setMessage(null);
    try {
      const accessToken = await getAccessToken();
      if (!mountedRef.current) return;
      if (!accessToken) throw new Error("Сессия истекла. Войдите снова и повторите отправку");
      const file = new File([result.blob], "meeting-recording.webm", { type: result.mimeType });
      const meeting = await createMeetingFromAudio(file, {
        ...metadata,
        recording_notice_confirmed: true,
      }, accessToken, "browser_recording");
      if (!mountedRef.current) return;
      setCreated(meeting);
      setState("preview");
      onCreated?.(meeting);
    } catch (error) {
      if (!mountedRef.current) return;
      const detail = error instanceof Error ? error.message : "Ошибка отправки";
      setMessage(`${detail}. Повторите отправку — запись сохранена в этой вкладке`);
      setState("preview");
      uploadingRef.current = false;
    }
  }

  return (
    <section aria-label="Записать вкладку" className="meeting-recorder">
      <p>Откройте веб-встречу, выберите её вкладку и включите передачу звука вкладки.</p>
      <p>Доступно в настольном Chrome или Edge на HTTPS или localhost. Звук микрофона записывается отдельно.</p>
      {state === "idle" || state === "error" ? (
        <button type="button" onClick={start}>Начать запись</button>
      ) : null}
      {state === "requesting" ? <p role="status">Ожидание разрешений браузера…</p> : null}
      {state === "recording" ? (
        <div>
          <p role="timer">Идёт запись вкладки · {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</p>
          <button type="button" onClick={stop}>Остановить</button>
        </div>
      ) : null}
      {state === "stopping" ? <p role="status">Завершаем аудиофайл…</p> : null}
      {result && previewUrl ? (
        <div>
          <p>Длительность: {Math.ceil(result.durationMs / 1000)} с · Размер: {(result.sizeBytes / 1024 / 1024).toFixed(1)} МиБ</p>
          <audio aria-label="Предпрослушивание записи" controls src={previewUrl} />
          <p>Запись хранится только в памяти этой вкладки и исчезнет после обновления страницы.</p>
          <label>
            <input type="checkbox" checked={noticeConfirmed} onChange={(event) => setNoticeConfirmed(event.target.checked)} disabled={Boolean(created)} />
            Участники уведомлены о записи
          </label>
          <div>
            <button type="button" onClick={() => { void remove(); }} disabled={state === "uploading"}>Удалить</button>
            <button type="button" onClick={() => { void upload(); }} disabled={state !== "preview" || !noticeConfirmed || Boolean(created) || result.sizeBytes > MAX_RECORDING_BYTES}>
              {state === "uploading" ? "Отправляем…" : "Завершить и обработать"}
            </button>
          </div>
        </div>
      ) : null}
      {message ? <p role="alert">{message}</p> : null}
      {created ? <p role="status">Встреча создана: {created.status}</p> : null}
    </section>
  );
}
