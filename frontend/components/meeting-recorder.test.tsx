import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { upload, startRecording, stopRecording, disposeRecording, callbacks, failureCallbacks } = vi.hoisted(() => ({
  upload: vi.fn(),
  startRecording: vi.fn(),
  stopRecording: vi.fn(),
  disposeRecording: vi.fn(),
  callbacks: [] as Array<(result: { blob: Blob; mimeType: string; durationMs: number; sizeBytes: number }, reason: string) => void>,
  failureCallbacks: [] as Array<(error: Error) => void>,
}));

vi.mock("@/lib/browser-recording", () => ({
  MAX_RECORDING_BYTES: 100 * 1024 * 1024,
  RecordingError: class RecordingError extends Error {},
  createBrowserRecording: (
    onFinished: (result: { blob: Blob; mimeType: string; durationMs: number; sizeBytes: number }, reason: string) => void,
    onFailed: (error: Error) => void,
  ) => {
    callbacks.push(onFinished);
    failureCallbacks.push(onFailed);
    return {
      startRecording,
      stopRecording,
      disposeRecording,
    };
  },
}));
vi.mock("@/lib/meetings-api", () => ({ createMeetingFromAudio: upload }));

import { MeetingRecorder } from "./meeting-recorder";

const metadata = {
  title: "План запуска",
  meeting_date: "2026-09-23",
  timezone: "Asia/Almaty",
  participants: ["Алия"],
  language_hint: "mixed" as const,
  recording_notice_confirmed: true,
};

beforeEach(() => {
  upload.mockReset();
  startRecording.mockReset().mockResolvedValue(undefined);
  stopRecording.mockReset();
  disposeRecording.mockReset().mockResolvedValue(undefined);
  callbacks.length = 0;
  failureCallbacks.length = 0;
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn(() => "blob:preview"),
    revokeObjectURL: vi.fn(),
  }));
  stopRecording.mockResolvedValue({
    blob: new Blob(["audio"], { type: "audio/webm" }),
    mimeType: "audio/webm",
    durationMs: 2500,
    sizeBytes: 5,
  });
});

afterEach(() => cleanup());

describe("meeting recorder preview", () => {
  it("lets the user review and delete the in-memory recording", async () => {
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    fireEvent.click(screen.getByRole("button", { name: "Остановить" }));
    await screen.findByRole("button", { name: "Удалить" });
    expect(screen.getByLabelText("Предпрослушивание записи")).toHaveAttribute("src", "blob:preview");
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(screen.queryByLabelText("Предпрослушивание записи")).not.toBeInTheDocument();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview");
  });

  it("retains preview after network failure and retries the same file", async () => {
    upload.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce({
      id: "meeting-id", status: "queued", source: { kind: "browser_recording" },
    });
    const onCreated = vi.fn();
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} onCreated={onCreated} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    fireEvent.click(screen.getByRole("button", { name: "Остановить" }));
    await screen.findByRole("button", { name: "Завершить и обработать" });
    fireEvent.click(screen.getByRole("checkbox", { name: /участники уведомлены/i }));
    fireEvent.click(screen.getByRole("button", { name: "Завершить и обработать" }));
    await screen.findByText(/Повторите отправку/);
    expect(screen.getByLabelText("Предпрослушивание записи")).toHaveAttribute("src", "blob:preview");
    fireEvent.click(screen.getByRole("button", { name: "Завершить и обработать" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledOnce());
    expect(upload).toHaveBeenCalledTimes(2);
    expect(screen.getByText(/queued/)).toBeInTheDocument();
  });

  it("requires notice confirmation again for a new recording", async () => {
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    fireEvent.click(screen.getByRole("button", { name: "Остановить" }));
    await screen.findByRole("button", { name: "Удалить" });
    fireEvent.click(screen.getByRole("checkbox", { name: /участники уведомлены/i }));
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    await screen.findByRole("button", { name: "Начать запись" });
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    fireEvent.click(screen.getByRole("button", { name: "Остановить" }));
    const submit = await screen.findByRole("button", { name: "Завершить и обработать" });
    expect(screen.getByRole("checkbox", { name: /участники уведомлены/i })).not.toBeChecked();
    expect(submit).toBeDisabled();
  });

  it("shows a reviewable preview when recording stops at the size limit", async () => {
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    const result = await stopRecording();
    act(() => callbacks[0](result, "size_limit"));
    expect(screen.getByLabelText("Предпрослушивание записи")).toHaveAttribute("src", "blob:preview");
    expect(screen.getByRole("alert")).toHaveTextContent(/лимита размера/);
    expect(screen.queryByRole("button", { name: "Остановить" })).not.toBeInTheDocument();
  });

  it.each(["display_ended", "audio_ended"])("shows a preview when %s ends with audio", async (reason) => {
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    const result = await stopRecording();
    act(() => callbacks[0](result, reason));
    expect(screen.getByLabelText("Предпрослушивание записи")).toHaveAttribute("src", "blob:preview");
    expect(screen.getByRole("alert")).toHaveTextContent(/демонстрация или звук остановлены/i);
    expect(screen.queryByRole("button", { name: "Остановить" })).not.toBeInTheDocument();
  });

  it("offers a fresh recording after automatic stop produces no audio", async () => {
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    act(() => failureCallbacks[0](new Error("Запись не создала аудиофайл. Попробуйте снова")));
    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("Запись не создала аудиофайл. Попробуйте снова");
    expect(screen.queryByRole("button", { name: "Остановить" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Предпрослушивание записи")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await waitFor(() => expect(startRecording).toHaveBeenCalledTimes(2));
  });

  it("does not notify the parent when an upload resolves after unmount", async () => {
    let finishUpload!: (meeting: { id: string; status: string; source: { kind: string } }) => void;
    upload.mockReturnValue(new Promise((resolve) => { finishUpload = resolve; }));
    const onCreated = vi.fn();
    const { unmount } = render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} onCreated={onCreated} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    fireEvent.click(screen.getByRole("button", { name: "Остановить" }));
    await screen.findByRole("button", { name: "Завершить и обработать" });
    fireEvent.click(screen.getByRole("checkbox", { name: /участники уведомлены/i }));
    fireEvent.click(screen.getByRole("button", { name: "Завершить и обработать" }));
    await waitFor(() => expect(upload).toHaveBeenCalledOnce());
    unmount();
    await act(async () => { finishUpload({ id: "late", status: "queued", source: { kind: "browser_recording" } }); });
    expect(onCreated).not.toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview");
  });

  it("starts only one upload for repeated submit clicks", async () => {
    let finishUpload!: (meeting: { id: string; status: string; source: { kind: string } }) => void;
    upload.mockReturnValue(new Promise((resolve) => { finishUpload = resolve; }));
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    fireEvent.click(screen.getByRole("button", { name: "Остановить" }));
    const submit = await screen.findByRole("button", { name: "Завершить и обработать" });
    fireEvent.click(screen.getByRole("checkbox", { name: /участники уведомлены/i }));
    act(() => { submit.click(); submit.click(); });
    await waitFor(() => expect(upload).toHaveBeenCalled());
    expect(upload).toHaveBeenCalledTimes(1);
    await act(async () => { finishUpload({ id: "one", status: "queued", source: { kind: "browser_recording" } }); });
  });

  it("opens only one capture request for repeated start clicks", async () => {
    let finishStart!: () => void;
    startRecording.mockReturnValue(new Promise<void>((resolve) => { finishStart = resolve; }));
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    const start = screen.getByRole("button", { name: "Начать запись" });
    act(() => { start.click(); start.click(); });
    expect(startRecording).toHaveBeenCalledTimes(1);
    await act(async () => { finishStart(); });
  });

  it("lets the user start again after stopping fails", async () => {
    stopRecording.mockRejectedValueOnce(new Error("encoder failed"));
    render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    fireEvent.click(screen.getByRole("button", { name: "Остановить" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await waitFor(() => expect(startRecording).toHaveBeenCalledTimes(2));
  });

  it("ignores recorder completion after unmount", async () => {
    const { unmount } = render(<MeetingRecorder metadata={metadata} getAccessToken={async () => "token"} />);
    fireEvent.click(screen.getByRole("button", { name: "Начать запись" }));
    await screen.findByRole("button", { name: "Остановить" });
    unmount();
    const result = await stopRecording();
    act(() => callbacks[0](result, "display_ended"));
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
