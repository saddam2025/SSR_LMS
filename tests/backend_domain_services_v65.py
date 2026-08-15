from io import BytesIO
from app.services.media import valid_upload_signature, normalize_media_type, media_return_path
from app.services.commerce import discounted_total

class Coupon:
    discount_percent = 25

assert valid_upload_signature(b'%PDF-1.7\n', 'application/pdf')
assert valid_upload_signature(b'\x89PNG\r\n\x1a\nxxx', 'image/png')
assert not valid_upload_signature(b'notpdf', 'application/pdf')
assert normalize_media_type('lesson.pdf', 'application/octet-stream') == ('application/pdf','application/pdf')
assert normalize_media_type('photo.jpg', 'image/jpeg') == ('image/jpeg','image/jpeg')
assert discounted_total(200, Coupon()) == 150.0
assert discounted_total(200, None) == 200.0
assert media_return_path(4, 9, '/evil') == '/admin/course/4#media-library'
print('backend_domain_services_v65: OK')
