@echo off
setlocal EnableDelayedExpansion
cd /d %~dp0
set PYTHONPATH=.
if "%ENV%"=="" set ENV=development
python -m compileall -q app tests || exit /b 1
for %%T in (tests\smoke_test.py tests\security_smoke.py tests\account_sharing_v37_flow.py tests\protected_assets_v37_flow.py tests\video_protection_v36_flow.py tests\video_watermark_v39_flow.py tests\cloudflare_v40_flow.py tests\lecture_upload_v57.py tests\full_menu_render_check.py tests\navigation_contract.py tests\end_to_end_final_flow.py tests\grade_v32_flow.py tests\video_feature_flow.py tests\video_control_center_flow.py tests\release_check_v40.py tests\release_audit.py tests\production_release_gate.py tests\ultimate_release.py) do (
  set DBFILE=%TEMP%\mostashar_v53_%%~nT_%RANDOM%.db
  if exist "!DBFILE!" del /q "!DBFILE!"
  set DATABASE_URL=sqlite:///!DBFILE:\=/!
  echo ===== %%T =====
  python %%T || exit /b 1
  if exist "!DBFILE!" del /q "!DBFILE!"
)
for /f %%V in (VERSION) do echo %%V RELEASE GATE OK
