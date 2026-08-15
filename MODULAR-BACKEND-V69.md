# Mostashar V69 — Courses & Lessons Router Extraction

V69 continues the modular backend migration without changing public URLs.

## Extracted
- Course create/toggle/update and admin course detail.
- Lesson edit/update/create/reorder/publish/delete.
- Lesson drip rules and per-student access overrides.
- Lesson video profile controls.
- Checkpoints, flashcards and offline policy administration.
- Video URL validation is now available from `app/services/courses.py`.

## Deliberately not moved yet
Student lesson playback, signed/protected video delivery, progress tracking, homework and quiz flows remain in their existing modules until their own bounded migration. This avoids coupling content administration back to protected media delivery.

## Compatibility
All HTTP paths and methods are preserved. `app.main.validated_video_url` remains as a compatibility wrapper during the migration.
