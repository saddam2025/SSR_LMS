# Modular Backend V76

V76 extracts homepage, academic content/revision, and remediation/smart-tutor domains from the legacy application module.

## New modules
- `app/routers/homepage.py`
- `app/services/homepage.py`
- `app/routers/academic_content.py`
- `app/services/academic_content.py`
- `app/routers/remediation.py`
- `app/services/remediation.py`

The public route contract remains stable while `app/main.py` is reduced to 1466 lines.
