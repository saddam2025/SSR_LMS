# Mostashar V63 — Separated Learning Center

V63 moves the remaining core student learning surfaces to the separated frontend/API architecture:

- Quiz list, server-owned quiz attempts, timer metadata, and server-side grading.
- Homework list/detail/submission.
- Notifications and read-all mutation with CSRF.
- Authorized search across enrolled courses, lessons, and quizzes.
- Study plan generated from accessible lessons and pending homework.
- New static frontend pages: `learning.html`, `quiz.html`, `homework.html`.

Security invariants:

- Correct quiz answers are not returned before submission.
- Quiz grading and attempt limits remain backend decisions.
- State-changing endpoints require HttpOnly session + CSRF header.
- Search and study-plan results are filtered by enrollment, publication, scheduling, and lesson access.
- The legacy backend HTML surfaces remain available as fallback during migration.
