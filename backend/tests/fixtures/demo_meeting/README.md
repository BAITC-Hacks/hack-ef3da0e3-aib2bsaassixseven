# Synthetic contract fixture

`synthetic.json` is immutable test data bound to a test-only owner UUID and by SHA-256 to a generated 0.0125-second silent WAV. Its transcript and insights are explicitly fictional. It validates prepared-example seeding, source labeling, owner isolation, and review behavior; it is **not** an ASR evaluation or a stage-ready recording.

For a stage demo, make a separate private fixture from an actual consented recording. Pin its dedicated `demo_owner_id` and audio SHA-256, manually verify every segment and evidence interval against the recording, and set `purpose` to `prepared_demo`. Keep the audio and any private transcripts out of Git. Seed it only into the dedicated demo Supabase account. The fixture source label must remain visible in the UI and PDF.
