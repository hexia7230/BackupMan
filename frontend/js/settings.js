/**
 * settings.js - Handling app configuration setup and export/import
 */

async function initSettings() {
  try {
    const res = await API.getSettingsStatus();
    const el = document.getElementById('current-setting-path');
    if (res && res.path) {
      el.textContent = res.path;
    } else {
      el.textContent = 'Not configured';
    }
  } catch (e) {
    showToast('Failed to load settings status: ' + e.message, 'error');
  }
}

async function createNewSetting() {
  try {
    const res = await API.saveFileDialog();
    if (res && res.path) {
      await API.createSettings(res.path);
      showToast('Created new setting file at ' + res.path, 'success');
      window.location.href = '/';
    }
  } catch (e) {
    showToast('Error creating setting: ' + e.message, 'error');
  }
}

async function importSetting() {
  try {
    const res = await API.openFileDialog();
    if (res && res.path) {
      await API.importSettings(res.path);
      showToast('Successfully imported settings from ' + res.path, 'success');
      window.location.href = '/';
    }
  } catch (e) {
    // Show extensive error when import fails
    showToast('Error importing settings: ' + e.message, 'error');
  }
}

async function exportSetting() {
  if (window._settingsConfigured === false) {
    showToast('Create or import setting file first.', 'error');
    return;
  }
  try {
    const res = await API.saveFileDialog();
    if (res && res.path) {
      await API.exportSettings(res.path);
      showToast('Successfully exported settings to ' + res.path, 'success');
    }
  } catch (e) {
    showToast('Error exporting settings: ' + e.message, 'error');
  }
}
