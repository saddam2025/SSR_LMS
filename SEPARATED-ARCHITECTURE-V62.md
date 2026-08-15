# Mostashar V62 — Separated Lesson Interactions

V62 continues the gradual frontend/backend separation without weakening server-side authorization.

## Moved to the separated frontend
- Interactive lesson checkpoints.
- Content-grounded lesson assistant.
- Lesson discussion list and posting.

## Security contract
- Every write uses the authenticated HttpOnly session and `X-CSRF-Token`.
- Enrollment, publish state, content scheduling and drip access are re-checked in the backend on every interaction.
- Checkpoint correct answers are returned only after an answer is submitted.
- Point awards remain idempotent per student/checkpoint.
- Discussion authorship comes from the authenticated session; the browser cannot choose the author.
- The separated UI renders user discussion text as text, not HTML.
- The assistant remains grounded in teacher-provided lesson/homework/checkpoint/flashcard content; no API secret is exposed to the frontend.

## Compatibility
The legacy Jinja lesson page and its interaction routes remain available as a fallback during migration.
