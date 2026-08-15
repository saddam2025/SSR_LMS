# Modular Backend V72

Student learning runtime is now independent from `app.main` at the router level. Rendering, protected lesson-context assembly, and study intelligence live in dedicated services. `app.main` remains the FastAPI bootstrap plus legacy/admin areas that have not yet been extracted.
