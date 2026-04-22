const TOKEN_KEY = 'soj-auth-token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function getUserEmail() {
  const token = getToken();
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split('.')[1])).email || null;
  } catch {
    return null;
  }
}

export function isLoggedIn() {
  const token = getToken();
  if (!token) return false;
  try {
    const { exp } = JSON.parse(atob(token.split('.')[1]));
    return exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
}

async function post(path, body) {
  const res = await fetch('/auth' + path, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json()).error || msg; } catch {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

export async function login(email, password) {
  const data = await post('/login', { email, password });
  localStorage.setItem(TOKEN_KEY, data.access_token);
}

export async function register(email, password, invitationToken) {
  const data = await post('/register', { email, password, invitation_token: invitationToken });
  localStorage.setItem(TOKEN_KEY, data.access_token);
}

export async function resetRequest(email) {
  await post('/reset-request', { email });
}

export async function resetConfirm(token, newPassword) {
  await post('/reset-confirm', { token, new_password: newPassword });
}
