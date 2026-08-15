# Modular Backend V65

V65 introduces domain services for protected media and commerce. Public URLs remain unchanged.

Next safe migration target: move thin HTTP handlers into dedicated `routers/media.py` and `routers/commerce.py` after shared auth/render/audit dependencies are extracted into reusable modules.
