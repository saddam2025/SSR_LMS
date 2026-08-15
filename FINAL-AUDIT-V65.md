# Mostashar V65 — Domain Services Hardening

V65 continues the backend modularization started in V64 without changing public routes.

## Changes
- Added `app/services/media.py` for Stream status normalization, upload signature/structure validation, MIME normalization, and safe media return paths.
- Added `app/services/commerce.py` for coupon resolution, discounted totals, and paid-entitlement activation.
- Refactored existing HTTP handlers to call these services while preserving route contracts and authorization behavior.
- Added `tests/backend_domain_services_v65.py`.

## Validation
Passed: Python compile, V65 domain service contract, Media Integrity V56, Resumable Lecture Upload V57, Commerce Center V14, Backend Modularization V64, Auth HTTP Contract V53, Navigation Contract, separated frontend V59–V63, Protected Assets V37, Video Watermark V39.

One combined test command exceeded the execution timeout after V62; remaining tests were rerun separately and passed.

## Architecture note
This release intentionally separates business logic before moving the most security-sensitive HTTP routes into dedicated routers. This avoids circular dependencies and keeps rollback straightforward.
