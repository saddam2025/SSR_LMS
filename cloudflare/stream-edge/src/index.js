const UID_RE = /^[A-Za-z0-9_-]{20,128}$/;
const CUSTOMER_CODE_RE = /^[A-Za-z0-9_-]{4,128}$/;

function textResponse(status, message) {
  return new Response(message, {
    status,
    headers: {
      'content-type': 'text/plain; charset=utf-8',
      'cache-control': 'no-store, private',
      'referrer-policy': 'no-referrer',
      'x-content-type-options': 'nosniff',
      'x-frame-options': 'DENY',
    },
  });
}

function decodeBase64Url(value) {
  if (!/^[A-Za-z0-9_-]+$/.test(value || '')) throw new Error('invalid_base64url');
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function verifyGrant(grant, routeUid, secret) {
  if (!grant || typeof grant !== 'string' || grant.length > 2048) return false;
  if (!secret || secret.length < 32) return false;
  const pieces = grant.split('.');
  if (pieces.length !== 2) return false;
  const [payloadPart, signaturePart] = pieces;
  try {
    const encoder = new TextEncoder();
    const key = await crypto.subtle.importKey(
      'raw',
      encoder.encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify'],
    );
    const signature = decodeBase64Url(signaturePart);
    const ok = await crypto.subtle.verify('HMAC', key, signature, encoder.encode(payloadPart));
    if (!ok) return false;

    const payload = new TextDecoder().decode(decodeBase64Url(payloadPart));
    const fields = payload.split('|');
    if (fields.length !== 6) return false;
    const [version, uid, lessonId, userId, expiry, nonce] = fields;
    if (version !== 'v1' || uid !== routeUid || !UID_RE.test(uid)) return false;
    if (!/^\d+$/.test(lessonId) || !/^\d+$/.test(userId)) return false;
    if (!/^\d{10,13}$/.test(expiry) || !/^[A-Za-z0-9_-]{8,64}$/.test(nonce)) return false;

    const now = Math.floor(Date.now() / 1000);
    const expiresAt = Number(expiry);
    // The Railway application intentionally issues grants for <= 300 seconds.
    // Reject expired grants and abnormally long-lived/replayed payloads.
    if (!Number.isSafeInteger(expiresAt) || expiresAt < now || expiresAt > now + 300) return false;
    return true;
  } catch (_) {
    return false;
  }
}

export default {
  async fetch(request, env) {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return textResponse(405, 'Method Not Allowed');
    }

    const url = new URL(request.url);
    const match = url.pathname.match(/^\/_edge\/stream\/([A-Za-z0-9_-]{20,128})$/);
    if (!match) return textResponse(404, 'Not Found');
    const uid = match[1];
    const grant = url.searchParams.get('grant') || '';

    const authorized = await verifyGrant(grant, uid, env.CF_EDGE_SIGNING_SECRET || '');
    if (!authorized) return textResponse(403, 'Forbidden');
    if (!env.STREAM || typeof env.STREAM.video !== 'function') {
      return textResponse(503, 'Stream binding is not configured');
    }

    const customerCode = String(env.CF_STREAM_CUSTOMER_CODE || '').trim();
    if (!CUSTOMER_CODE_RE.test(customerCode)) {
      return textResponse(503, 'Stream customer code is not configured');
    }

    try {
      const token = await env.STREAM.video(uid).generateToken();
      if (!token || typeof token !== 'string') return textResponse(502, 'Unable to generate playback token');
      const destination = `https://customer-${customerCode}.cloudflarestream.com/${token}/iframe`;
      return new Response(null, {
        status: 302,
        headers: {
          location: destination,
          'cache-control': 'no-store, private',
          pragma: 'no-cache',
          'referrer-policy': 'no-referrer',
          'x-content-type-options': 'nosniff',
        },
      });
    } catch (_) {
      return textResponse(502, 'Unable to generate playback token');
    }
  },
};
