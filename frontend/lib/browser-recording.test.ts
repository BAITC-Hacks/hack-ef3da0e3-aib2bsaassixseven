import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createBrowserRecording } from "./browser-recording";

class FakeTrack extends EventTarget {
  readyState: MediaStreamTrackState = "live";
  stop = vi.fn(() => { this.readyState = "ended"; });
  constructor(readonly kind: "audio" | "video", readonly surface?: string) { super(); }
  getSettings() { return { displaySurface: this.surface }; }
}

class FakeStream {
  constructor(readonly tracks: FakeTrack[]) {}
  getTracks() { return this.tracks; }
  getAudioTracks() { return this.tracks.filter((track) => track.kind === "audio"); }
  getVideoTracks() { return this.tracks.filter((track) => track.kind === "video"); }
}

class FakeNode {
  connect = vi.fn();
  disconnect = vi.fn();
}

const destinationTrack = new FakeTrack("audio");
const sources: FakeNode[] = [];
const destination = Object.assign(new FakeNode(), { stream: new FakeStream([destinationTrack]) });

class FakeAudioContext {
  state = "running";
  createMediaStreamSource = vi.fn((_stream: MediaStream) => {
    void _stream;
    const node = new FakeNode();
    sources.push(node);
    return node;
  });
  createMediaStreamDestination = vi.fn(() => destination);
  close = vi.fn(async () => { this.state = "closed"; });
}

class FakeRecorder extends EventTarget {
  static created: FakeRecorder;
  static emitDataOnStop = true;
  static isTypeSupported = vi.fn((type: string) => type === "audio/webm;codecs=opus");
  state: RecordingState = "inactive";
  mimeType: string;
  start = vi.fn(() => { this.state = "recording"; });
  stop = vi.fn(() => {
    this.state = "inactive";
    if (FakeRecorder.emitDataOnStop) this.chunk(new Blob(["audio bytes"], { type: this.mimeType }));
    this.dispatchEvent(new Event("stop"));
  });
  constructor(readonly stream: MediaStream, options: MediaRecorderOptions) {
    super();
    this.mimeType = options.mimeType ?? "";
    FakeRecorder.created = this;
  }
  chunk(data: Blob) {
    this.dispatchEvent(Object.assign(new Event("dataavailable"), { data }));
  }
}

const tabVideo = new FakeTrack("video", "browser");
const tabAudio = new FakeTrack("audio");
const microphone = new FakeTrack("audio");
const display = new FakeStream([tabVideo, tabAudio]);
const mic = new FakeStream([microphone]);
const getDisplayMedia = vi.fn(async () => display as unknown as MediaStream);
const getUserMedia = vi.fn(async () => mic as unknown as MediaStream);

beforeEach(() => {
  FakeRecorder.emitDataOnStop = true;
  getDisplayMedia.mockClear();
  getUserMedia.mockClear();
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("navigator", { mediaDevices: { getDisplayMedia, getUserMedia } });
  getDisplayMedia.mockResolvedValue(display as unknown as MediaStream);
  getUserMedia.mockResolvedValue(mic as unknown as MediaStream);
  for (const track of [tabVideo, tabAudio, microphone, destinationTrack]) {
    track.readyState = "live";
    track.stop.mockClear();
  }
  sources.length = 0;
  FakeRecorder.isTypeSupported.mockClear();
});

afterEach(() => vi.unstubAllGlobals());

describe("browser recording", () => {
  it("rejects a selected surface without an audio track and releases video", async () => {
    getDisplayMedia.mockResolvedValueOnce(new FakeStream([tabVideo]) as unknown as MediaStream);
    const recording = createBrowserRecording();
    await expect(recording.startRecording()).rejects.toMatchObject({ code: "tab_audio_missing" });
    expect(tabVideo.stop).toHaveBeenCalledOnce();
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it("releases captured display tracks when microphone permission is denied", async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException("denied", "NotAllowedError"));
    const recording = createBrowserRecording();
    await expect(recording.startRecording()).rejects.toMatchObject({ code: "microphone_denied" });
    expect(tabVideo.stop).toHaveBeenCalledOnce();
    expect(tabAudio.stop).toHaveBeenCalledOnce();
  });

  it("rejects a window share before requesting the microphone", async () => {
    const windowVideo = new FakeTrack("video", "window");
    getDisplayMedia.mockResolvedValueOnce(new FakeStream([windowVideo, tabAudio]) as unknown as MediaStream);
    const recording = createBrowserRecording();

    await expect(recording.startRecording()).rejects.toMatchObject({ code: "wrong_surface" });
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(windowVideo.stop).toHaveBeenCalledOnce();
    expect(tabAudio.stop).toHaveBeenCalledOnce();
  });

  it("releases display capture granted after disposal", async () => {
    let grantDisplay!: (stream: MediaStream) => void;
    getDisplayMedia.mockReturnValueOnce(new Promise((resolve) => { grantDisplay = resolve; }));
    const finished = vi.fn();
    const recording = createBrowserRecording(finished);
    const starting = recording.startRecording();
    await recording.disposeRecording();
    grantDisplay(display as unknown as MediaStream);

    await expect(starting).rejects.toMatchObject({ code: "capture_cancelled" });
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(tabVideo.stop).toHaveBeenCalledOnce();
    expect(tabAudio.stop).toHaveBeenCalledOnce();
    expect(finished).not.toHaveBeenCalled();
  });

  it("releases microphone capture granted after disposal", async () => {
    let grantMicrophone!: (stream: MediaStream) => void;
    getUserMedia.mockReturnValueOnce(new Promise((resolve) => { grantMicrophone = resolve; }));
    const recording = createBrowserRecording();
    const starting = recording.startRecording();
    await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
    await recording.disposeRecording();
    grantMicrophone(mic as unknown as MediaStream);

    await expect(starting).rejects.toMatchObject({ code: "capture_cancelled" });
    expect(tabVideo.stop).toHaveBeenCalledOnce();
    expect(tabAudio.stop).toHaveBeenCalledOnce();
    expect(microphone.stop).toHaveBeenCalledOnce();
  });

  it("refuses to record when tab sharing ends during the microphone prompt", async () => {
    let grantMicrophone!: (stream: MediaStream) => void;
    getUserMedia.mockReturnValueOnce(new Promise((resolve) => { grantMicrophone = resolve; }));
    const recording = createBrowserRecording();
    const starting = recording.startRecording();
    await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
    tabVideo.readyState = "ended";
    grantMicrophone(mic as unknown as MediaStream);

    await expect(starting).rejects.toMatchObject({ code: "display_ended" });
    expect(tabAudio.stop).toHaveBeenCalledOnce();
    expect(microphone.stop).toHaveBeenCalledOnce();
  });

  it("refuses to record when tab audio ends during the microphone prompt", async () => {
    let grantMicrophone!: (stream: MediaStream) => void;
    getUserMedia.mockReturnValueOnce(new Promise((resolve) => { grantMicrophone = resolve; }));
    const recording = createBrowserRecording();
    const starting = recording.startRecording();
    await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
    tabAudio.readyState = "ended";
    grantMicrophone(mic as unknown as MediaStream);

    await expect(starting).rejects.toMatchObject({ code: "tab_audio_missing" });
    expect(tabVideo.stop).toHaveBeenCalledOnce();
    expect(microphone.stop).toHaveBeenCalledOnce();
  });

  it("records the mixed audio stream and finalizes once after repeated stop", async () => {
    const recording = createBrowserRecording();
    await recording.startRecording();
    expect(FakeRecorder.created.stream).toBe(destination.stream);
    expect(FakeRecorder.created.stream.getVideoTracks()).toHaveLength(0);
    const [first, second] = await Promise.all([recording.stopRecording(), recording.stopRecording()]);
    expect(first).toBe(second);
    expect(first.mimeType).toBe("audio/webm;codecs=opus");
    expect(first.blob.size).toBeGreaterThan(0);
    expect(FakeRecorder.created.stop).toHaveBeenCalledOnce();
    for (const track of [tabVideo, tabAudio, microphone]) expect(track.stop).toHaveBeenCalledOnce();
    expect(sources).toHaveLength(2);
    for (const source of sources) expect(source.disconnect).toHaveBeenCalledOnce();
  });

  it("finishes when browser sharing ends", async () => {
    const finished = vi.fn();
    const recording = createBrowserRecording(finished);
    await recording.startRecording();
    tabVideo.dispatchEvent(new Event("ended"));
    await vi.waitFor(() => expect(finished).toHaveBeenCalledOnce());
    expect(finished.mock.calls[0][1]).toBe("display_ended");
    expect(FakeRecorder.created.stop).toHaveBeenCalledOnce();
  });

  it("finishes with an encoding error reason when MediaRecorder fails", async () => {
    const finished = vi.fn();
    const recording = createBrowserRecording(finished);
    await recording.startRecording();
    FakeRecorder.created.dispatchEvent(new Event("error"));

    await vi.waitFor(() => expect(finished).toHaveBeenCalledOnce());
    expect(finished.mock.calls[0][1]).toBe("encoding_error");
    expect(FakeRecorder.created.stop).toHaveBeenCalledOnce();
    expect(tabVideo.stop).toHaveBeenCalledOnce();
    expect(microphone.stop).toHaveBeenCalledOnce();
  });

  it("waits for the final chunk after recorder error has made it inactive", async () => {
    const finished = vi.fn();
    const recording = createBrowserRecording(finished);
    await recording.startRecording();
    const recorder = FakeRecorder.created;
    recorder.state = "inactive";
    recorder.dispatchEvent(new Event("error"));
    recorder.chunk(new Blob(["last audio"], { type: recorder.mimeType }));
    recorder.dispatchEvent(new Event("stop"));

    await vi.waitFor(() => expect(finished).toHaveBeenCalledOnce());
    expect(finished.mock.calls[0][0].sizeBytes).toBe(10);
    expect(finished.mock.calls[0][1]).toBe("encoding_error");
  });

  it("reports a failed automatic stop when no audio chunk was encoded", async () => {
    FakeRecorder.emitDataOnStop = false;
    const failed = vi.fn();
    const recording = createBrowserRecording(undefined, failed);
    await recording.startRecording();
    tabVideo.dispatchEvent(new Event("ended"));

    await vi.waitFor(() => expect(failed).toHaveBeenCalledOnce());
    expect(failed.mock.calls[0][0]).toMatchObject({ code: "encoding_error" });
    expect(tabAudio.stop).toHaveBeenCalledOnce();
    expect(microphone.stop).toHaveBeenCalledOnce();
  });

  it("stops automatically before accumulated data reaches 100 MiB", async () => {
    const finished = vi.fn();
    const recording = createBrowserRecording(finished);
    await recording.startRecording();
    FakeRecorder.created.chunk(new Blob([new Uint8Array(95 * 1024 * 1024)]));
    await vi.waitFor(() => expect(finished).toHaveBeenCalledOnce());
    expect(FakeRecorder.created.stop).toHaveBeenCalledOnce();
    expect(finished.mock.calls[0][1]).toBe("size_limit");
  });
});
