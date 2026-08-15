# V60 separated architecture

The browser-facing student dashboard and course catalog live in `platform/frontend`. FastAPI remains the system of record and authorization boundary.

## Backend modules
- `app/api_v1.py`: compatibility aggregator.
- `app/api_v1_session.py`: session bootstrap and CSRF-protected logout.
- `app/api_v1_student.py`: student course/lesson/summary/notification APIs.
- `app/api_v1_common.py`: shared API user resolution.
- `app/access.py`: shared enrollment, scheduling and drip-content authorization used by both legacy and API paths.

## Security boundary
Frontend rendering never decides enrollment or lesson unlock state. The backend returns only authorized records. Raw lesson `video_url` is not returned by the V60 student API. Playback remains on the existing protected backend lesson route until its media authorization flow is migrated separately.
