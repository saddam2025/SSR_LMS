from pathlib import Path


def test_csp_allows_only_configured_r2_endpoint_for_direct_upload():
    code = Path("app/main.py").read_text(encoding="utf-8")
    assert 's3_endpoint = os.getenv("S3_ENDPOINT_URL", "").strip()' in code
    assert 'connect_sources.append(f"https://{parsed_s3.hostname}")' in code
    assert "connect-src https:" not in code


def test_direct_upload_client_puts_to_presigned_url():
    code = Path("app/static/admin-media-upload.js").read_text(encoding="utf-8")
    assert 'xhr.open("PUT", url, true)' in code
    assert "init.upload_url" in code
