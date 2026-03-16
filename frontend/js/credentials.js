/**
 * credentials.js - Credentials management page.
 */

// ─── Init ─────────────────────────────────────────────────────────────────────

async function initCredentials() {
  await loadCredentialsList();
}

// ─── List ─────────────────────────────────────────────────────────────────────

async function loadCredentialsList() {
  const tbody = document.getElementById('cred-table-body');
  if (!tbody) return;

  try {
    const creds = await API.getCredentials();

    if (!creds.length) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state">
        <div class="empty-state-title">No credentials stored.</div>
        <div class="empty-state-sub">Add credentials for UNC network share access.</div>
      </div></td></tr>`;
      return;
    }

    tbody.innerHTML = creds.map(c => `<tr>
      <td>${escHtml(c.label)}</td>
      <td class="text-mono text-sm">${escHtml(c.server)}</td>
      <td class="text-sm">${escHtml(c.username)}</td>
      <td class="text-sm text-secondary">${formatDatetime(c.created_at)}</td>
      <td>
        <button class="btn btn-danger btn-sm" onclick="deleteCredential('${escHtml(c.id)}')">Delete</button>
      </td>
    </tr>`).join('');
  } catch (e) {
    showToast('Failed to load credentials: ' + e.message, 'error');
  }
}

// ─── Add Credential Modal ─────────────────────────────────────────────────────

function openAddCredModal() {
  document.getElementById('cred-label').value = '';
  document.getElementById('cred-server').value = '';
  document.getElementById('cred-username').value = '';
  document.getElementById('cred-password').value = '';
  document.getElementById('cred-test-path').value = '';
  document.getElementById('cred-validate-msg').textContent = '';
  document.getElementById('cred-validate-msg').className = '';
  document.getElementById('add-cred-modal').classList.add('open');
}

function closeAddCredModal() {
  document.getElementById('add-cred-modal').classList.remove('open');
}

async function saveCredential() {
  const label    = document.getElementById('cred-label').value.trim();
  const server   = document.getElementById('cred-server').value.trim();
  const username = document.getElementById('cred-username').value.trim();
  const password = document.getElementById('cred-password').value;
  const testPath = document.getElementById('cred-test-path').value.trim();
  const msgEl    = document.getElementById('cred-validate-msg');

  if (!label || !server || !username || !password) {
    msgEl.textContent = 'All fields are required.';
    msgEl.className = 'form-error';
    return;
  }

  msgEl.textContent = 'Validating connection...';
  msgEl.className = 'form-hint';

  const saveBtn = document.getElementById('btn-save-cred');
  saveBtn.disabled = true;

  try {
    await API.createCredential({
      label, server, username, password,
      test_path: testPath || server,
    });
    showToast('Credential saved and validated.', 'success');
    closeAddCredModal();
    loadCredentialsList();
  } catch (e) {
    msgEl.textContent = 'Failed: ' + e.message;
    msgEl.className = 'form-error';
  } finally {
    saveBtn.disabled = false;
  }
}

async function deleteCredential(id) {
  if (!confirm('Delete this credential? Schedules using it will lose access.')) return;
  try {
    await API.deleteCredential(id);
    showToast('Credential deleted.', 'success');
    loadCredentialsList();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}
