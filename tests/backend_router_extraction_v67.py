import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
os.environ.setdefault('DATABASE_URL','sqlite:///./v67_router_test.db')
os.environ.setdefault('ENV','test')
os.environ.setdefault('APP_SECRET','v67-test-secret')

from app.main import app
from app.routers import media, commerce

media_paths = {
    '/admin/lesson/{lesson_id}/stream-upload/init',
    '/admin/lesson/{lesson_id}/stream-upload/finalize',
    '/admin/lesson/{lesson_id}/stream-upload/status',
    '/admin/course/{course_id}/media',
    '/admin/media/{asset_id}/delete',
    '/protected/media/{asset_id}',
}
commerce_paths = {
    '/checkout/{course_id}', '/api/paymob/webhook', '/payment/complete',
    '/admin/commerce', '/admin/coupons', '/admin/coupons/{coupon_id}/toggle',
    '/admin/subscriptions/grant', '/admin/subscriptions/{subscription_id}/extend',
    '/admin/subscriptions/{subscription_id}/status',
}

def route_paths(router):
    return {r.path for r in router.routes}

assert media_paths <= route_paths(media.router)
assert commerce_paths <= route_paths(commerce.router)

# Same path+method must be registered only once in the final app.
seen = set()
for r in app.routes:
    methods = getattr(r, 'methods', None) or set()
    for method in methods:
        key = (method, r.path)
        assert key not in seen, f'duplicate route: {key}'
        seen.add(key)

for path in media_paths | commerce_paths:
    assert any(r.path == path for r in app.routes), path

print('V67 MEDIA + COMMERCE ROUTER EXTRACTION: PASS')
