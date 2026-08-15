#!/usr/bin/env python3
"""V83 DNS/TLS readiness checker.

Checks DNS resolution and HTTPS/TLS reachability for API and frontend hostnames.
Does not require or print credentials.
"""
from __future__ import annotations
import argparse, json, socket, ssl, time
from pathlib import Path
from urllib.parse import urlparse


def check_url(label: str, url: str) -> dict:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    result = {"check": label, "url": url, "host": host, "dns": False, "tls": False, "status": "FAIL", "detail": ""}
    if parsed.scheme != "https" or not host:
        result["detail"] = "must be a valid HTTPS URL"
        return result
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = sorted({i[4][0] for i in infos})
        result["dns"] = bool(ips)
        result["resolved_count"] = len(ips)
    except Exception as exc:
        result["detail"] = f"DNS failed: {type(exc).__name__}"
        return result
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=8) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
                result["tls"] = True
                result["tls_version"] = tls.version()
                result["cert_subject_present"] = bool(cert)
        result["status"] = "PASS"
        result["detail"] = "DNS resolution and TLS handshake ok"
    except Exception as exc:
        result["detail"] = f"TLS failed: {type(exc).__name__}"
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="https://staging-api.ragab-seddik.com")
    p.add_argument("--frontend", default="https://staging-student.ragab-seddik.com")
    p.add_argument("--json-report", type=Path)
    args = p.parse_args()
    checks = [check_url("staging_api_dns_tls", args.api), check_url("staging_frontend_dns_tls", args.frontend)]
    failed = [x for x in checks if x["status"] != "PASS"]
    print("V83 DNS/TLS READINESS")
    for x in checks:
        print(f"[{x['status']}] {x['check']}: {x['detail']}")
    summary = {"timestamp": int(time.time()), "checks": checks, "go": not failed}
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("GO" if not failed else "NO-GO")
    return 0 if not failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
