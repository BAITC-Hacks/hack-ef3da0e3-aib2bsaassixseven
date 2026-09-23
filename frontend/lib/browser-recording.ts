export type RecordingErrorCode =
  | "unsupported"
  | "insecure_context"
  | "capture_cancelled"
  | "tab_audio_missing"
  | "wrong_surface"
  | "microphone_denied"
  | "display_ended"
  | "encoding_error"
  | "size_limit";

export class RecordingError extends Error {
  constructor(readonly code: RecordingErrorCode, message: string) {
    super(message);
    this.name = "RecordingError";
  }
}

export type RecordingResult = {
  blob: Blob;
  mimeType: string;
  durationMs: number;
  sizeBytes: number;
};

export type StopReason = "manual" | "display_ended" | "audio_ended" | "size_limit" | "encoding_error";
export const MAX_RECORDING_BYTES = 100 * 1024 * 1024;
const STOP_AT_BYTES = 95 * 1024 * 1024;

function stopTracks(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

function chooseMimeType(): string {
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
  if (MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
  throw new RecordingError("unsupported", "Запись не поддерживается в этом браузере");
}

function permissionError(error: unknown, code: RecordingErrorCode): RecordingError {
  if (error instanceof DOMException && ["NotAllowedError", "AbortError"].includes(error.name)) {
    return new RecordingError(code, code === "microphone_denied"
      ? "Разрешите доступ к микрофону и попробуйте снова"
      : "Выбор вкладки отменён. Выберите вкладку конференции и включите её звук");
  }
  return new RecordingError(code, code === "microphone_denied"
    ? "Не удалось получить звук микрофона"
    : "Не удалось захватить вкладку");
}

class BrowserRecording {
  private display: MediaStream | null = null;
  private microphone: MediaStream | null = null;
  private context: AudioContext | null = null;
  private sources: MediaStreamAudioSourceNode[] = [];
  private destination: MediaStreamAudioDestinationNode | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private bytes = 0;
  private startedAt = 0;
  private mimeType = "";
  private stopPromise: Promise<RecordingResult> | null = null;
  private state: "idle" | "requesting" | "recording" | "stopping" | "finished" = "idle";
  private disposed = false;
  private stopReason: StopReason = "manual";
  private listeners: Array<() => void> = [];

  constructor(
    private readonly onFinished?: (result: RecordingResult, reason: StopReason) => void,
    private readonly onFailed?: (error: RecordingError) => void,
  ) {}

  private stopAutomatically(reason: StopReason): void {
    void this.stopRecording(reason).catch((error: unknown) => {
      if (!this.disposed) {
        this.onFailed?.(error instanceof RecordingError
          ? error
          : new RecordingError("encoding_error", "Запись прервана. Попробуйте снова"));
      }
    });
  }

  async startRecording(): Promise<void> {
    if (this.disposed || this.state !== "idle") throw new RecordingError("unsupported", "Запись уже запущена");
    if (window.isSecureContext === false) throw new RecordingError("insecure_context", "Откройте сайт по HTTPS или localhost");
    if (!navigator.mediaDevices?.getDisplayMedia || !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined" || typeof AudioContext === "undefined") {
      throw new RecordingError("unsupported", "Запись не поддерживается в этом браузере");
    }
    this.mimeType = chooseMimeType();
    this.state = "requesting";
    try {
      // Call directly from the click handler's synchronous path to keep transient activation.
      let displayRequest: Promise<MediaStream>;
      try {
        displayRequest = navigator.mediaDevices.getDisplayMedia({
          audio: true,
          video: { displaySurface: "browser" },
        });
      } catch (error) {
        throw permissionError(error, "capture_cancelled");
      }
      try {
        this.display = await displayRequest;
      } catch (error) {
        throw permissionError(error, "capture_cancelled");
      }
      if (this.disposed) throw new RecordingError("capture_cancelled", "Запись отменена");
      const video = this.display.getVideoTracks()[0];
      const tabAudio = this.display.getAudioTracks()[0];
      if (!video || !tabAudio || tabAudio.readyState !== "live") {
        throw new RecordingError("tab_audio_missing", "Выберите вкладку конференции и включите передачу её звука");
      }
      if (video.readyState !== "live") {
        throw new RecordingError("display_ended", "Демонстрация вкладки остановлена. Попробуйте снова");
      }
      const surface = video.getSettings().displaySurface;
      if (surface && surface !== "browser") {
        throw new RecordingError("wrong_surface", "Выберите вкладку браузера, а не окно или экран");
      }
      try {
        // The tab may omit the local microphone, so capture it separately.
        this.microphone = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true }, video: false,
        });
      } catch (error) {
        throw permissionError(error, "microphone_denied");
      }
      if (this.disposed) throw new RecordingError("capture_cancelled", "Запись отменена");
      if (!this.microphone.getAudioTracks().some((track) => track.readyState === "live")) {
        throw new RecordingError("microphone_denied", "Не удалось получить звук микрофона");
      }
      if (video.readyState !== "live") {
        throw new RecordingError("display_ended", "Демонстрация вкладки остановлена. Попробуйте снова");
      }
      if (tabAudio.readyState !== "live") {
        throw new RecordingError("tab_audio_missing", "Звук вкладки остановлен. Попробуйте снова");
      }
      this.context = new AudioContext();
      const tabSource = this.context.createMediaStreamSource(this.display);
      const micSource = this.context.createMediaStreamSource(this.microphone);
      this.sources = [tabSource, micSource];
      this.destination = this.context.createMediaStreamDestination();
      tabSource.connect(this.destination);
      micSource.connect(this.destination);
      // Only the mixed audio destination is recorded; video is never encoded.
      this.recorder = new MediaRecorder(this.destination.stream, { mimeType: this.mimeType });
      this.listen(video, "ended", () => this.stopAutomatically("display_ended"));
      for (const track of [tabAudio, ...this.microphone.getAudioTracks()]) {
        this.listen(track, "ended", () => this.stopAutomatically("audio_ended"));
      }
      this.listen(this.recorder, "dataavailable", (event) => {
        const data = (event as BlobEvent).data;
        if (!data || data.size === 0) return;
        this.chunks.push(data);
        this.bytes += data.size;
        if (this.bytes >= STOP_AT_BYTES) this.stopAutomatically("size_limit");
      });
      this.listen(this.recorder, "error", () => {
        this.stopAutomatically("encoding_error");
      });
      this.startedAt = performance.now();
      this.recorder.start(1000);
      this.state = "recording";
    } catch (error) {
      this.state = "finished";
      await this.cleanup();
      throw error;
    }
  }

  stopRecording(reason: StopReason = "manual"): Promise<RecordingResult> {
    if (this.stopPromise) return this.stopPromise;
    if (this.state !== "recording" || !this.recorder) {
      return Promise.reject(new RecordingError("encoding_error", "Нет активной записи"));
    }
    this.state = "stopping";
    this.stopReason = reason;
    const recorder = this.recorder;
    this.stopPromise = new Promise<RecordingResult>((resolve, reject) => {
      const onStop = () => {
        recorder.removeEventListener("stop", onStop);
        void (async () => {
          const result: RecordingResult = {
            blob: new Blob(this.chunks, { type: recorder.mimeType || this.mimeType }),
            mimeType: recorder.mimeType || this.mimeType,
            durationMs: Math.max(0, performance.now() - this.startedAt),
            sizeBytes: this.bytes,
          };
          this.state = "finished";
          await this.cleanup();
          if (result.sizeBytes === 0) {
            reject(new RecordingError("encoding_error", "Запись не создала аудиофайл. Попробуйте снова"));
            return;
          }
          resolve(result);
          if (!this.disposed) this.onFinished?.(result, this.stopReason);
        })().catch(reject);
      };
      recorder.addEventListener("stop", onStop, { once: true });
      try {
        // An error makes MediaRecorder inactive before it emits its final
        // dataavailable and stop events; wait for stop to preserve that chunk.
        if (recorder.state !== "inactive") recorder.stop();
      } catch (error) {
        recorder.removeEventListener("stop", onStop);
        void this.cleanup().finally(() => reject(error));
      }
    });
    return this.stopPromise;
  }

  async disposeRecording(): Promise<void> {
    this.disposed = true;
    if (this.state === "recording") {
      await this.stopRecording().catch(() => {});
    } else if (this.stopPromise) {
      await this.stopPromise.catch(() => {});
    }
    await this.cleanup();
  }

  private listen(target: EventTarget, event: string, callback: EventListener): void {
    target.addEventListener(event, callback);
    this.listeners.push(() => target.removeEventListener(event, callback));
  }

  private async cleanup(): Promise<void> {
    this.listeners.splice(0).forEach((remove) => remove());
    stopTracks(this.display);
    stopTracks(this.microphone);
    stopTracks(this.destination?.stream ?? null);
    this.display = null;
    this.microphone = null;
    for (const source of this.sources) source.disconnect();
    this.sources = [];
    this.destination?.disconnect();
    this.destination = null;
    if (this.context && this.context.state !== "closed") await this.context.close();
    this.context = null;
    this.recorder = null;
  }
}

export function createBrowserRecording(
  onFinished?: (result: RecordingResult, reason: StopReason) => void,
  onFailed?: (error: RecordingError) => void,
) {
  return new BrowserRecording(onFinished, onFailed);
}
