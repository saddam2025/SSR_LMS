"""Railway pre-deploy entry point with precise stage diagnostics."""
from .preflight import run as run_preflight


def run() -> None:
    run_preflight()
    print("MOSTASHAR PREDEPLOY ADMIN: checking initial admin", flush=True)
    from .bootstrap_admin import run as run_bootstrap_admin
    run_bootstrap_admin()
    print("MOSTASHAR DEPLOY PREPARE OK", flush=True)


if __name__ == "__main__":
    run()
