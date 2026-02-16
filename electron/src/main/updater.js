/**
 * Auto-Updater Module
 */

const { app, ipcMain, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const { getMainWindow } = require('./window');

const RELEASES_URL = 'https://github.com/FX93Y2/db_simulator/releases/latest';

function sendToRenderer(channel, data) {
    const win = getMainWindow();
    if (win && !win.isDestroyed()) {
        win.webContents.send(channel, data);
    }
}

function initAutoUpdater() {
    if (!app.isPackaged) {
        console.log('[Updater] Skipping update check in development mode');
        return;
    }

    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = false;

    autoUpdater.on('checking-for-update', () => {
        console.log('[Updater] Checking for updates...');
    });

    autoUpdater.on('update-available', (info) => {
        console.log(`[Updater] Update available: v${info.version}`);
        sendToRenderer('updater:update-available', {
            version: info.version,
            releaseDate: info.releaseDate,
            releaseNotes: info.releaseNotes,
            releaseUrl: RELEASES_URL
        });
    });

    autoUpdater.on('update-not-available', (info) => {
        console.log(`[Updater] App is up to date (v${info.version})`);
        sendToRenderer('updater:update-not-available', {
            version: info.version
        });
    });

    autoUpdater.on('error', (error) => {
        console.error('[Updater] Error:', error.message);
        sendToRenderer('updater:error', {
            message: error.message
        });
    });

    ipcMain.handle('updater:check', async () => {
        try {
            const result = await autoUpdater.checkForUpdates();
            return { success: true, version: result?.updateInfo?.version };
        } catch (error) {
            console.error('[Updater] Manual check failed:', error.message);
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('updater:open-release-page', () => {
        console.log('[Updater] Opening release page:', RELEASES_URL);
        shell.openExternal(RELEASES_URL);
    });

    setTimeout(() => {
        console.log('[Updater] Running initial update check...');
        autoUpdater.checkForUpdates().catch((err) => {
            console.error('[Updater] Initial check failed:', err.message);
        });
    }, 5000);
}

module.exports = { initAutoUpdater };
