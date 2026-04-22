import { login, register, resetRequest, resetConfirm } from '../auth.js';

const overlay = document.getElementById('loginOverlay');

function showView(id) {
  overlay.querySelectorAll('.auth-view').forEach(v => { v.hidden = v.id !== id; });
}

function setError(viewId, msg) {
  const el = document.querySelector(`#${viewId} .auth-error`);
  if (!el) return;
  el.textContent = msg;
  el.hidden = !msg;
}

function setInfo(viewId, msg) {
  const el = document.querySelector(`#${viewId} .auth-info`);
  if (!el) return;
  el.textContent = msg;
  el.hidden = !msg;
}

function setBusy(viewId, busy) {
  const btn = document.querySelector(`#${viewId} button[type=submit]`);
  if (btn) btn.disabled = busy;
}

async function submit(viewId, fn) {
  setError(viewId, '');
  setBusy(viewId, true);
  try {
    await fn();
    document.dispatchEvent(new CustomEvent('auth:success'));
  } catch (err) {
    setError(viewId, err.message);
  } finally {
    setBusy(viewId, false);
  }
}

export function showLoginOverlay() {
  const params = new URLSearchParams(window.location.search);
  const resetToken  = params.get('reset');
  const inviteToken = params.get('invite');
  history.replaceState(null, '', window.location.pathname);
  if (resetToken) {
    document.getElementById('authResetToken').value = resetToken;
    showView('authReset');
  } else if (inviteToken) {
    document.getElementById('inviteToken').value = inviteToken;
    showView('authRegister');
    const emailEl = document.getElementById('registerEmail');
    emailEl.value    = '';
    emailEl.readOnly = true;
    setBusy('authRegister', true);
    fetch(`/auth/invite-info/${encodeURIComponent(inviteToken)}`)
      .then(r => r.ok ? r.json() : r.json().then(j => Promise.reject(j.error || 'Invitation invalide')))
      .then(data => { emailEl.value = data.email; })
      .catch(err => { setError('authRegister', err); })
      .finally(() => { setBusy('authRegister', false); });
  } else {
    showView('authLogin');
  }
  overlay.hidden = false;
}

export function hideLoginOverlay() {
  overlay.hidden = true;
}

export function initLoginOverlay() {
  document.getElementById('formLogin').addEventListener('submit', e => {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value.trim();
    const pw    = document.getElementById('loginPassword').value;
    submit('authLogin', () => login(email, pw));
  });

  document.getElementById('formRegister').addEventListener('submit', e => {
    e.preventDefault();
    const email  = document.getElementById('registerEmail').value.trim();
    const pw     = document.getElementById('registerPassword').value;
    const pw2    = document.getElementById('registerPassword2').value;
    const invite = document.getElementById('inviteToken').value;
    if (pw !== pw2) { setError('authRegister', 'Les mots de passe ne correspondent pas'); return; }
    submit('authRegister', () => register(email, pw, invite));
  });

  document.getElementById('formResetRequest').addEventListener('submit', async e => {
    e.preventDefault();
    const email = document.getElementById('resetEmail').value.trim();
    setError('authResetRequest', '');
    setBusy('authResetRequest', true);
    try {
      await resetRequest(email);
      setInfo('authResetRequest', 'Si ce compte existe, un e-mail a été envoyé.');
      document.getElementById('resetEmail').value = '';
    } catch (err) {
      setError('authResetRequest', err.message);
    } finally {
      setBusy('authResetRequest', false);
    }
  });

  document.getElementById('formReset').addEventListener('submit', async e => {
    e.preventDefault();
    const token = document.getElementById('authResetToken').value;
    const pw    = document.getElementById('newPassword').value;
    const pw2   = document.getElementById('newPassword2').value;
    if (pw !== pw2) { setError('authReset', 'Les mots de passe ne correspondent pas'); return; }
    setError('authReset', '');
    setBusy('authReset', true);
    try {
      await resetConfirm(token, pw);
      showView('authLogin');
      setInfo('authLogin', 'Mot de passe mis à jour. Connectez-vous.');
    } catch (err) {
      setError('authReset', err.message);
    } finally {
      setBusy('authReset', false);
    }
  });

  document.getElementById('linkToLogin').addEventListener('click',        e => { e.preventDefault(); showView('authLogin'); });
  document.getElementById('linkForgotPassword').addEventListener('click', e => { e.preventDefault(); showView('authResetRequest'); });
  document.getElementById('linkResetToLogin').addEventListener('click',   e => { e.preventDefault(); showView('authLogin'); });
}
