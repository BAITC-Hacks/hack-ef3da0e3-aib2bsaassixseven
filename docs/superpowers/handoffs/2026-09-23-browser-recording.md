# Browser recording branch handoff

Branch: `codex/browser-meeting-recording`, based on `main` at `10d65ec`.

This branch implements the browser tab recorder independently while stages 4–5 build the meeting UI and review flow. Do not merge it into a branch without the P0 meeting creation screen until the final UI connection is made.

## Interfaces for the stage 4–5 merge

- `frontend/components/meeting-recorder.tsx` exports `MeetingRecorder`. Render it beside the P0 file uploader inside the meeting creation Client Component. Pass the same `title`, `meeting_date`, `timezone`, `participants`, and `language_hint` values as `metadata`, with an async `getAccessToken` returning the current Supabase access token. Use `onCreated` to navigate to the existing meeting status screen after `202`.
- `frontend/lib/meetings-api.ts` exports `createMeetingFromAudio(file, metadata, accessToken, sourceKind)`. Make the P0 file uploader use this same function with the default `uploaded_audio` source, or reconcile it with any P0 client already added. It sends one native `FormData` request to the existing `POST /api/v1/meetings`.
- The backend accepts `source_kind: "browser_recording"` in JSON metadata and returns it as `source.kind`. Omitted `source_kind` still means `uploaded_audio`; `demo_fixture` stays private.
- Keep the P0 status polling, review, PDF, and temporary audio cleanup unchanged. The recorder uploads only after the user stops, previews, and confirms notice to participants.

## Merge checks

1. Resolve likely conflicts in `backend/app/api/routes/meetings.py`, `backend/app/services/artifact_store.py`, and `docs/technical/API_CONTRACT.md` against the stage 4–5 branch without dropping either review/PDF routes or the recording source contract.
2. Render the upload/record switch on the real creation screen, and ensure changing modes during capture disposes tracks. Wire `onCreated` into the existing `queued`/`processing` flow.
3. Run frontend Vitest, lint, typecheck, build; backend pytest, Ruff, Pyright after the merge.
4. On desktop Chrome or Edge, record a short permitted web call with two voices. Listen to the WebM for remote audio and microphone, then submit it and complete review and PDF export. Record the OS, browser version, and result in the PR.

The automated media tests use fakes and cannot prove that a specific browser/OS supplies an audio track for the selected tab.
