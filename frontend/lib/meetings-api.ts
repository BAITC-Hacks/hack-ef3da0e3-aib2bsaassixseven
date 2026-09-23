import { getPublicEnv } from "@/lib/env";

import { MAX_RECORDING_BYTES } from "@/lib/browser-recording";

export type MeetingUploadMetadata = {
  title: string;
  meeting_date: string;
  timezone: string;
  participants: string[];
  language_hint?: "auto" | "ru" | "kk" | "mixed";
  recording_notice_confirmed: boolean;
};

export type CreatedMeeting = {
  id: string;
  status: "queued" | "processing";
  source: { kind: "uploaded_audio" | "browser_recording" };
};

export class MeetingUploadError extends Error {
  constructor(readonly code: "network" | "rejected" | "too_large" | "invalid_response", message: string) {
    super(message);
    this.name = "MeetingUploadError";
  }
}

export async function createMeetingFromAudio(
  file: File,
  metadata: MeetingUploadMetadata,
  accessToken: string,
  sourceKind: "uploaded_audio" | "browser_recording" = "uploaded_audio",
  fetcher: typeof fetch = fetch,
): Promise<CreatedMeeting> {
  if (!metadata.recording_notice_confirmed) {
    throw new MeetingUploadError("rejected", "Подтвердите уведомление участников о записи");
  }
  if (!accessToken.trim()) {
    throw new MeetingUploadError("rejected", "Сессия истекла. Войдите снова и повторите отправку");
  }
  if (file.size > MAX_RECORDING_BYTES) {
    throw new MeetingUploadError("too_large", "Файл превышает 100 МиБ. Запишите встречу заново");
  }
  const body = new FormData();
  body.append("audio", file, file.name);
  body.append("metadata", JSON.stringify({ ...metadata, source_kind: sourceKind }));
  let response: Response;
  try {
    response = await fetcher(`${getPublicEnv().apiUrl}/api/v1/meetings`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      body,
    });
  } catch {
    throw new MeetingUploadError("network", "Сеть недоступна. Проверьте соединение и отправьте запись снова");
  }
  if (response.status !== 202) {
    throw new MeetingUploadError("rejected", response.status === 413
      ? "Сервер отклонил запись: файл превышает 100 МиБ"
      : "Сервер отклонил запись. Проверьте данные встречи и попробуйте снова");
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new MeetingUploadError("invalid_response", "Сервер вернул некорректный ответ");
  }
  if (typeof payload !== "object" || payload === null ||
    !("id" in payload) || typeof payload.id !== "string" ||
    !("status" in payload) || !["queued", "processing"].includes(String(payload.status)) ||
    !("source" in payload) || typeof payload.source !== "object" || payload.source === null ||
    !("kind" in payload.source) || payload.source.kind !== sourceKind) {
    throw new MeetingUploadError("invalid_response", "Сервер вернул некорректную встречу");
  }
  return payload as CreatedMeeting;
}
