from pathlib import Path
import argparse, shutil

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'frontend'
parser=argparse.ArgumentParser()
parser.add_argument('--environment', choices=['production','staging'], required=True)
parser.add_argument('--output', required=True)
args=parser.parse_args()
out=Path(args.output).resolve()
if out == SRC.resolve() or SRC.resolve() in out.parents:
    raise SystemExit('Output must be outside platform/frontend')
if out.exists(): shutil.rmtree(out)
shutil.copytree(SRC,out,ignore=shutil.ignore_patterns('config.staging.example.js','README.md'))
api='https://api.ragab-seddik.com' if args.environment=='production' else 'https://staging-api.ragab-seddik.com'
(out/'config.js').write_text(f'window.MOSTASHAR_CONFIG = {{\n  API_BASE: "{api}"\n}};\n',encoding='utf-8')
print(f'PAGES BUILD OK: {args.environment} -> {out} ({api})')
