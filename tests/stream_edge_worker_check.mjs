import { webcrypto } from 'node:crypto';
if (!globalThis.crypto) globalThis.crypto = webcrypto;
import worker from '../cloudflare/stream-edge/src/index.js';

const secret = 'edge-test-secret-' + 'x'.repeat(48);
const uid = 'a1b2c3d4e5f678901234567890abcdef';
const encoder = new TextEncoder();

function b64url(bytes) {
  return Buffer.from(bytes).toString('base64').replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
}

async function grantFor(routeUid, expOffset = 90) {
  const expires = Math.floor(Date.now() / 1000) + expOffset;
  const payload = `v1|${routeUid}|7|11|${expires}|nonceABC123`;
  const payloadPart = b64url(encoder.encode(payload));
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(payloadPart));
  return `${payloadPart}.${b64url(new Uint8Array(signature))}`;
}

const env = {
  CF_EDGE_SIGNING_SECRET: secret,
  CF_STREAM_CUSTOMER_CODE: 'demo-code',
  STREAM: {
    video(id) {
      if (id !== uid) throw new Error('wrong uid');
      return { async generateToken() { return 'signed.token.value'; } };
    },
  },
};

let grant = await grantFor(uid);
let res = await worker.fetch(new Request(`https://ragab-seddik.com/_edge/stream/${uid}?grant=${grant}`), env);
if (res.status !== 302) throw new Error(`expected 302, got ${res.status}`);
if (res.headers.get('location') !== 'https://customer-demo-code.cloudflarestream.com/signed.token.value/iframe') throw new Error('bad redirect');
if (!/no-store/.test(res.headers.get('cache-control') || '')) throw new Error('missing no-store');

res = await worker.fetch(new Request(`https://ragab-seddik.com/_edge/stream/${uid}`), env);
if (res.status !== 403) throw new Error('missing grant must be 403');

res = await worker.fetch(new Request(`https://ragab-seddik.com/_edge/stream/${uid}?grant=${grant.slice(0, -2)}xx`), env);
if (res.status !== 403) throw new Error('tampered grant must be 403');

const expired = await grantFor(uid, -10);
res = await worker.fetch(new Request(`https://ragab-seddik.com/_edge/stream/${uid}?grant=${expired}`), env);
if (res.status !== 403) throw new Error('expired grant must be 403');

const tooLong = await grantFor(uid, 600);
res = await worker.fetch(new Request(`https://ragab-seddik.com/_edge/stream/${uid}?grant=${tooLong}`), env);
if (res.status !== 403) throw new Error('overlong grant must be 403');

console.log('STREAM EDGE WORKER CHECK OK');
