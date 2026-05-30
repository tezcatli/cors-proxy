import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { getToken, getUserEmail, isLoggedIn, logout, login, register, resetRequest, resetConfirm, apiFetch } from '../src/lib/auth.js';
import { AUTH, mockResponse } from './contract.js';

// Stub the router so apiFetch's lazy redirect-to-login import is inert in tests.
vi.mock('../src/router.js', () => ({
  default: { currentRoute: { value: { path: '/' } }, push: vi.fn() },
}));

const TOKEN_KEY = 'soj-auth-token';

function makeToken({ email = 'user@test.com', expOffsetSeconds = 3600 } = {}) {
  const now = Math.floor(Date.now() / 1000);
  const payload = { sub: '1', email, iat: now, exp: now + expOffsetSeconds };
  return `x.${btoa(JSON.stringify(payload))}.y`;
}

beforeEach(() => { localStorage.clear(); });

// ── getToken ──────────────────────────────────────────────────────────────

describe('getToken', () => {
  it('returns empty string when nothing is stored', () => {
    expect(getToken()).toBe('');
  });
  it('returns the stored token', () => {
    localStorage.setItem(TOKEN_KEY, 'mytoken');
    expect(getToken()).toBe('mytoken');
  });
});

// ── getUserEmail ──────────────────────────────────────────────────────────

describe('getUserEmail', () => {
  it('returns null when no token', () => {
    expect(getUserEmail()).toBeNull();
  });
  it('extracts email from a valid token', () => {
    localStorage.setItem(TOKEN_KEY, makeToken({ email: 'alice@example.com' }));
    expect(getUserEmail()).toBe('alice@example.com');
  });
  it('returns null for a malformed token', () => {
    localStorage.setItem(TOKEN_KEY, 'not.a.token');
    expect(getUserEmail()).toBeNull();
  });
});

// ── isLoggedIn ────────────────────────────────────────────────────────────

describe('isLoggedIn', () => {
  it('returns false when no token', () => {
    expect(isLoggedIn()).toBe(false);
  });
  it('returns true for a valid, non-expired token', () => {
    localStorage.setItem(TOKEN_KEY, makeToken({ expOffsetSeconds: 3600 }));
    expect(isLoggedIn()).toBe(true);
  });
  it('returns false for an expired token', () => {
    localStorage.setItem(TOKEN_KEY, makeToken({ expOffsetSeconds: -1 }));
    expect(isLoggedIn()).toBe(false);
  });
  it('returns false for a malformed token', () => {
    localStorage.setItem(TOKEN_KEY, 'bad.token');
    expect(isLoggedIn()).toBe(false);
  });
});

// ── logout ────────────────────────────────────────────────────────────────

describe('logout', () => {
  it('removes the token from localStorage', () => {
    localStorage.setItem(TOKEN_KEY, makeToken());
    logout();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(isLoggedIn()).toBe(false);
  });
});

// ── apiFetch 401 handling ───────────────────────────────────────────────────

describe('apiFetch 401 handling', () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it('clears the token on a 401 from a protected endpoint', async () => {
    localStorage.setItem(TOKEN_KEY, makeToken());
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 401, json: vi.fn().mockResolvedValue({ error: 'Not authenticated' }),
    }));
    await expect(apiFetch('/silence/games')).rejects.toThrow('Not authenticated');
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('does NOT clear the token on a 401 from an auth endpoint (bad login)', async () => {
    localStorage.setItem(TOKEN_KEY, makeToken());
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 401, json: vi.fn().mockResolvedValue({ error: 'E-mail ou mot de passe incorrect' }),
    }));
    await expect(login('x@x.com', 'wrong')).rejects.toThrow('E-mail ou mot de passe incorrect');
    expect(localStorage.getItem(TOKEN_KEY)).not.toBeNull();
  });
});

// ── login ─────────────────────────────────────────────────────────────────

describe('login', () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it('stores the access token on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(AUTH.login.success, { access_token: 'server-token-abc' })
    ));
    await login('user@test.com', 'password');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('server-token-abc');
  });

  it('throws on bad credentials', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(AUTH.login.bad_credentials, { error: 'Invalid credentials' })
    ));
    await expect(login('x@x.com', 'wrong')).rejects.toThrow('Invalid credentials');
  });

  it('falls back to HTTP status when server returns no error message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: AUTH.login.bad_credentials.status,
      json: vi.fn().mockRejectedValue(new Error('not json')),
    }));
    await expect(login('x@x.com', 'pw')).rejects.toThrow(`HTTP ${AUTH.login.bad_credentials.status}`);
  });
});

// ── register ──────────────────────────────────────────────────────────────

describe('register', () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it('stores the access token on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(AUTH.register.success, { access_token: 'new-token-xyz' })
    ));
    await register('new@test.com', 'password8', 'invite-token');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('new-token-xyz');
  });

  it('throws on bad invitation token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(AUTH.register.invalid_invite, { error: 'Invitation invalide' })
    ));
    await expect(register('a@b.com', 'password8', 'bad')).rejects.toThrow('Invitation invalide');
  });

  it('throws on duplicate email', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(AUTH.register.duplicate_email, { error: 'Adresse déjà utilisée' })
    ));
    await expect(register('dup@b.com', 'password8', 'tok')).rejects.toThrow('Adresse déjà utilisée');
  });
});

// ── resetRequest ──────────────────────────────────────────────────────────

describe('resetRequest', () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it('resolves without error on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(AUTH.reset_request.success)
    ));
    await expect(resetRequest('user@test.com')).resolves.toBeUndefined();
  });
});

// ── resetConfirm ──────────────────────────────────────────────────────────

describe('resetConfirm', () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it('resolves without error on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(AUTH.reset_confirm.success)
    ));
    await expect(resetConfirm('reset-token', 'newpassword')).resolves.toBeUndefined();
  });

  it('throws on expired token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      mockResponse(AUTH.reset_confirm.expired_token, { error: 'Ce lien a expiré' })
    ));
    await expect(resetConfirm('old-token', 'newpassword')).rejects.toThrow('Ce lien a expiré');
  });
});
