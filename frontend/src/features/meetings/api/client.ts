import { z } from "zod";

import {
  type AccessTokenProvider,
  getSupabaseAccessToken,
} from "@/lib/supabase/access-token";
import {
  normalizeApiUrl,
  publicEnv,
} from "@/lib/config/public-env";

import {
  approvalRequestSchema,
  insightsSchema,
  meetingApiErrorPayloadSchema,
  type MeetingApiDomainErrorCode,
  type MeetingListParams,
  meetingListParamsSchema,
  type MeetingPage,
  meetingPageSchema,
  type Meeting,
  meetingIdSchema,
  meetingSchema,
  type MeetingUploadMetadata,
  meetingUploadMetadataSchema,
  type ReviewRequest,
  type ReviewResponse,
  reviewRequestSchema,
  reviewResponseSchema,
  type Transcript,
  transcriptSchema,
  type Insights,
} from "./schemas";

export const MAX_MEETING_UPLOAD_BYTES = 100 * 1024 * 1024;

const supportedFileExtensions = new Set([
  "wav",
  "mp3",
  "m4a",
  "ogg",
  "webm",
  "mp4",
  "mov",
  "mkv",
]);
const accessTokenSchema = z.string().trim().min(1);

export type MeetingApiErrorCode =
  | MeetingApiDomainErrorCode
  | "authentication_required"
  | "network"
  | "invalid_response";

export class MeetingApiError extends Error {
  constructor(
    readonly code: MeetingApiErrorCode,
    message: string,
    readonly status: number | null = null,
  ) {
    super(message);
    this.name = "MeetingApiError";
  }
}

export type MeetingApiOptions = {
  apiUrl?: string;
  fetcher?: typeof fetch;
  getAccessToken?: AccessTokenProvider;
  signal?: AbortSignal;
};

const domainMessages: Record<MeetingApiDomainErrorCode, string> = {
  invalid_request: "Check the meeting details and try again.",
  meeting_not_found: "Meeting not found.",
  invalid_state: "This action is not available in the meeting's current state.",
  file_too_large: "The file exceeds the 100 MiB limit.",
  unsupported_media_type:
    "Choose a supported WAV, MP3, M4A, OGG, WebM, MP4, MOV, or MKV recording.",
  storage_failed: "The meeting service could not save the data. Try again.",
  attempts_exhausted: "This meeting has reached the processing retry limit.",
  source_expired: "The temporary recording expired. Upload the recording again.",
  cleanup_pending: "Temporary-data cleanup is still in progress. Try again shortly.",
  delete_failed: "The meeting could not be deleted. Try again.",
  stale_revision: "This meeting changed elsewhere. Reload it before saving again.",
  review_required: "Review and approve the current revision before exporting.",
  export_failed: "The PDF could not be created. Try again.",
  queue_unavailable: "Processing is temporarily unavailable. Try again.",
  gpu_unavailable: "The processing server is temporarily unavailable. Try again.",
  invalid_result: "The processing result could not be verified.",
};

function invalidRequest(message = domainMessages.invalid_request): MeetingApiError {
  return new MeetingApiError("invalid_request", message, null);
}

function validatedMeetingId(meetingId: string): string {
  const result = meetingIdSchema.safeParse(meetingId);
  if (!result.success) throw invalidRequest();
  return result.data;
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "AbortError"
  );
}

function statusFallback(response: Response): MeetingApiError {
  if (response.status === 401 || response.status === 403) {
    return new MeetingApiError(
      "authentication_required",
      "Your session expired. Sign in again and retry.",
      response.status,
    );
  }
  if (response.status === 404) {
    return new MeetingApiError(
      "meeting_not_found",
      domainMessages.meeting_not_found,
      response.status,
    );
  }
  if (response.status === 413) {
    return new MeetingApiError(
      "file_too_large",
      domainMessages.file_too_large,
      response.status,
    );
  }
  if (response.status === 415) {
    return new MeetingApiError(
      "unsupported_media_type",
      domainMessages.unsupported_media_type,
      response.status,
    );
  }
  if (response.status === 422) {
    return new MeetingApiError(
      "invalid_request",
      domainMessages.invalid_request,
      response.status,
    );
  }

  return new MeetingApiError(
    "invalid_response",
    response.status >= 500
      ? "The meeting service is temporarily unavailable. Try again."
      : "The meeting service could not complete the request.",
    response.status,
  );
}

async function responseError(response: Response): Promise<MeetingApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return statusFallback(response);
  }

  const parsed = meetingApiErrorPayloadSchema.safeParse(payload);
  if (!parsed.success) return statusFallback(response);

  return new MeetingApiError(
    parsed.data.code,
    domainMessages[parsed.data.code],
    response.status,
  );
}

async function request(
  path: `/${string}`,
  init: RequestInit,
  options: MeetingApiOptions,
): Promise<Response> {
  const tokenProvider = options.getAccessToken ?? getSupabaseAccessToken;
  let token: string;
  try {
    const result = accessTokenSchema.safeParse(await tokenProvider());
    if (!result.success) throw new Error("Missing access token");
    token = result.data;
  } catch {
    throw new MeetingApiError(
      "authentication_required",
      "Your session expired. Sign in again and retry.",
      null,
    );
  }

  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);

  const apiUrl = normalizeApiUrl(options.apiUrl ?? publicEnv.NEXT_PUBLIC_API_URL);
  const fetcher = options.fetcher ?? fetch;
  try {
    return await fetcher(`${apiUrl}${path}`, {
      ...init,
      cache: "no-store",
      headers,
      signal: options.signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new MeetingApiError(
      "network",
      "The meeting service could not be reached. Check the connection and try again.",
      null,
    );
  }
}

async function expectJson<T>(
  response: Response,
  expectedStatus: number,
  schema: z.ZodType<T>,
): Promise<T> {
  if (!response.ok) throw await responseError(response);
  if (response.status !== expectedStatus) {
    throw new MeetingApiError(
      "invalid_response",
      "The meeting service returned an unexpected response.",
      response.status,
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new MeetingApiError(
      "invalid_response",
      "The meeting service returned an unreadable response.",
      response.status,
    );
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new MeetingApiError(
      "invalid_response",
      "The meeting service returned data in an unsupported format.",
      response.status,
    );
  }
  return parsed.data;
}

function jsonRequest(body: unknown): RequestInit {
  return {
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  };
}

export async function listMeetings(
  params: MeetingListParams = {},
  options: MeetingApiOptions = {},
): Promise<MeetingPage> {
  const parsed = meetingListParamsSchema.safeParse(params);
  if (!parsed.success) throw invalidRequest();

  const search = new URLSearchParams();
  if (parsed.data.limit !== undefined) {
    search.set("limit", String(parsed.data.limit));
  }
  if (parsed.data.cursor !== undefined) {
    search.set("cursor", parsed.data.cursor);
  }
  const query = search.size > 0 ? `?${search.toString()}` : "";
  const response = await request(`/meetings${query}`, { method: "GET" }, options);
  return expectJson(response, 200, meetingPageSchema);
}

export async function getMeeting(
  meetingId: string,
  options: MeetingApiOptions = {},
): Promise<Meeting> {
  const id = validatedMeetingId(meetingId);
  const response = await request(`/meetings/${id}`, { method: "GET" }, options);
  return expectJson(response, 200, meetingSchema);
}

export async function createMeeting(
  file: File,
  metadata: MeetingUploadMetadata,
  options: MeetingApiOptions = {},
): Promise<Meeting> {
  if (file.size === 0) {
    throw invalidRequest("Choose a non-empty meeting audio file.");
  }
  if (file.size > MAX_MEETING_UPLOAD_BYTES) {
    throw new MeetingApiError("file_too_large", domainMessages.file_too_large);
  }
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!extension || !supportedFileExtensions.has(extension)) {
    throw new MeetingApiError(
      "unsupported_media_type",
      domainMessages.unsupported_media_type,
    );
  }

  const parsed = meetingUploadMetadataSchema.safeParse(metadata);
  if (!parsed.success) throw invalidRequest();

  const body = new FormData();
  body.append("audio", file, file.name);
  body.append("metadata", JSON.stringify(parsed.data));
  const response = await request(
    "/meetings",
    { method: "POST", body },
    options,
  );
  return expectJson(response, 202, meetingSchema);
}

export async function getTranscript(
  meetingId: string,
  options: MeetingApiOptions = {},
): Promise<Transcript> {
  const id = validatedMeetingId(meetingId);
  const response = await request(
    `/meetings/${id}/transcript`,
    { method: "GET" },
    options,
  );
  return expectJson(response, 200, transcriptSchema);
}

export async function getInsights(
  meetingId: string,
  options: MeetingApiOptions = {},
): Promise<Insights> {
  const id = validatedMeetingId(meetingId);
  const response = await request(
    `/meetings/${id}/insights`,
    { method: "GET" },
    options,
  );
  return expectJson(response, 200, insightsSchema);
}

export async function updateReview(
  meetingId: string,
  review: ReviewRequest,
  options: MeetingApiOptions = {},
): Promise<ReviewResponse> {
  const id = validatedMeetingId(meetingId);
  const parsed = reviewRequestSchema.safeParse(review);
  if (!parsed.success) throw invalidRequest();
  const response = await request(
    `/meetings/${id}/review`,
    { method: "PUT", ...jsonRequest(parsed.data) },
    options,
  );
  return expectJson(response, 200, reviewResponseSchema);
}

export async function approveMeeting(
  meetingId: string,
  baseRevision: number,
  options: MeetingApiOptions = {},
): Promise<Meeting> {
  const id = validatedMeetingId(meetingId);
  const parsed = approvalRequestSchema.safeParse({
    base_revision: baseRevision,
  });
  if (!parsed.success) throw invalidRequest();
  const response = await request(
    `/meetings/${id}/approve`,
    { method: "POST", ...jsonRequest(parsed.data) },
    options,
  );
  return expectJson(response, 200, meetingSchema);
}

export async function retryMeeting(
  meetingId: string,
  options: MeetingApiOptions = {},
): Promise<Meeting> {
  const id = validatedMeetingId(meetingId);
  const response = await request(
    `/meetings/${id}/retry`,
    { method: "POST" },
    options,
  );
  return expectJson(response, 202, meetingSchema);
}

export async function deleteMeeting(
  meetingId: string,
  options: MeetingApiOptions = {},
): Promise<void> {
  const id = validatedMeetingId(meetingId);
  const response = await request(
    `/meetings/${id}`,
    { method: "DELETE" },
    options,
  );
  if (!response.ok) throw await responseError(response);
  if (response.status !== 204) {
    throw new MeetingApiError(
      "invalid_response",
      "The meeting service returned an unexpected response.",
      response.status,
    );
  }
}

export async function downloadMeetingPdf(
  meetingId: string,
  options: MeetingApiOptions = {},
): Promise<Blob> {
  const id = validatedMeetingId(meetingId);
  const response = await request(
    `/meetings/${id}/export.pdf`,
    { method: "GET", headers: { Accept: "application/pdf" } },
    options,
  );
  if (!response.ok) throw await responseError(response);
  if (response.status !== 200) {
    throw new MeetingApiError(
      "invalid_response",
      "The meeting service returned an unexpected response.",
      response.status,
    );
  }

  const contentType = response.headers.get("Content-Type")?.split(";", 1)[0];
  if (contentType !== "application/pdf") {
    throw new MeetingApiError(
      "invalid_response",
      "The meeting service returned an invalid PDF response.",
      response.status,
    );
  }
  const pdf = await response.blob();
  if (pdf.size === 0) {
    throw new MeetingApiError(
      "invalid_response",
      "The meeting service returned an empty PDF.",
      response.status,
    );
  }
  return pdf;
}
