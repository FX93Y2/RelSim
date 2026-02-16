/**
 * Main Electron Process - Modular Architecture
 * Orchestrates all application modules and manages the application lifecycle
 */

const { app, powerMonitor } = require('electron');
const path = require('path');

// Import modular components
const { getAppPaths } = require('./src/main/paths');
const { createWindow } = require('./src/main/window');
const { startBackend, stopBackend } = require('./src/main/backend');
const { registerApiHandlers } = require('./src/main/api-handlers');
const { initAutoUpdater } = require('./src/main/updater');

// Application state
let appPaths = null;
let isAppReady = false;

// Mitigation for GPU/IPC glitches after hibernate/resume (common on WSL/WSLg)
// Disable hardware acceleration and force software GL before app 'ready'
try {
  app.disableHardwareAcceleration();
  app.commandLine.appendSwitch('use-gl', 'swiftshader');
  console.log('Hardware acceleration disabled; using SwiftShader (software GL)');
} catch (e) {
  console.warn('Failed to set GPU/GL switches:', e);
}

/**
 * Initialize the application
 */
async function initializeApp() {
  try {
    console.log('Initializing Database Simulator Application...');

    // Get and setup application paths
    appPaths = getAppPaths();
    console.log('Application paths configured successfully');

    // Start the backend
    console.log('Starting backend services...');
    startBackend(appPaths);

    // Register all API handlers
    console.log('Registering API handlers...');
    registerApiHandlers(appPaths);

    // Create the main window
    console.log('Creating main window...');
    const preloadPath = path.join(__dirname, 'preload.js');
    createWindow(preloadPath);

    // Initialize auto-updater
    console.log('Initializing auto-updater...');
    initAutoUpdater();

    isAppReady = true;
    console.log('Application initialized successfully');

  } catch (error) {
    console.error('Error initializing application:', error);
    app.quit();
  }
}

/**
 * Cleanup resources when the application is closing
 */
function cleanup() {
  console.log('Cleaning up application resources...');

  // Stop the backend process
  stopBackend();

  console.log('Cleanup completed');
}

/**
 * Application lifecycle event handlers
 */

// App ready event - called when Electron has finished initialization
app.on('ready', () => {
  console.log('Electron ready event received');
  initializeApp();
});

// On system resume, reload the window to rebind renderer/IPC cleanly
powerMonitor.on('resume', () => {
  try {
    console.log('System resume detected; reloading main window');
    const { getMainWindow } = require('./src/main/window');
    const win = getMainWindow();
    if (win && !win.isDestroyed()) {
      win.webContents.reloadIgnoringCache();
    }
  } catch (e) {
    console.warn('Error handling resume:', e);
  }
});

// Window all closed event - called when all windows have been closed
app.on('window-all-closed', () => {
  console.log('All windows closed');

  // On macOS it is common for applications and their menu bar
  // to stay active until the user quits explicitly with Cmd + Q
  if (process.platform !== 'darwin') {
    console.log('Quitting application (non-macOS platform)');
    app.quit();
  }
});

// Activate event - called when the application is activated (macOS)
app.on('activate', () => {
  console.log('Application activate event received');

  // On macOS it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open
  const { getMainWindow } = require('./src/main/window');
  if (getMainWindow() === null && isAppReady) {
    console.log('Re-creating main window');
    const preloadPath = path.join(__dirname, 'preload.js');
    createWindow(preloadPath);
  }
});

// Will quit event - called before the application starts closing windows
app.on('will-quit', () => {
  console.log('Application will quit event received');
  cleanup();
});

// Before quit event - allows preventing the quit
app.on('before-quit', (event) => {
  console.log('Application before quit event received');
  // Perform any final cleanup here if needed
});

// Recover from GPU/renderer crashes by reloading the main window
app.on('child-process-gone', (_event, details) => {
  try {
    if (details && (details.type === 'GPU' || details.reason === 'crashed')) {
      console.warn('Child process gone:', details);
      const { getMainWindow } = require('./src/main/window');
      const win = getMainWindow();
      if (win && !win.isDestroyed()) {
        win.webContents.reloadIgnoringCache();
      }
    }
  } catch (e) {
    console.warn('Error handling child-process-gone:', e);
  }
});

// Legacy GPU crash event (some Electron versions)
app.on('gpu-process-crashed', () => {
  try {
    console.warn('GPU process crashed; reloading main window');
    const { getMainWindow } = require('./src/main/window');
    const win = getMainWindow();
    if (win && !win.isDestroyed()) {
      win.webContents.reloadIgnoringCache();
    }
  } catch (e) {
    console.warn('Error handling gpu-process-crashed:', e);
  }
});

// Certificate error handling for development
app.on('certificate-error', (event, webContents, url, error, certificate, callback) => {
  if (process.env.NODE_ENV === 'development') {
    // In development, ignore certificate errors for localhost
    if (url.startsWith('https://localhost') || url.startsWith('https://127.0.0.1')) {
      event.preventDefault();
      callback(true);
      return;
    }
  }

  // In production, use default behavior
  callback(false);
});

// Handle protocol for deep linking (if needed in the future)
app.setAsDefaultProtocolClient('db-simulator');

// Security: Prevent new window creation from renderer
app.on('web-contents-created', (event, contents) => {
  contents.on('new-window', (event, navigationUrl) => {
    // Prevent opening new windows
    event.preventDefault();
    console.warn(`Blocked new window creation to: ${navigationUrl}`);
  });

  // Prevent navigation to external URLs
  contents.on('will-navigate', (event, navigationUrl) => {
    const parsedUrl = new URL(navigationUrl);

    // Allow navigation to local files and localhost
    if (
      parsedUrl.protocol !== 'file:' &&
      parsedUrl.hostname !== 'localhost' &&
      parsedUrl.hostname !== '127.0.0.1'
    ) {
      event.preventDefault();
      console.warn(`Blocked navigation to external URL: ${navigationUrl}`);
    }
  });
});

// Handle unhandled promise rejections
process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Promise Rejection at:', promise, 'reason:', reason);
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  console.error('Uncaught Exception:', error);
});

// Handle termination signals
if (process.platform === 'win32') {
  require('readline').createInterface({
    input: process.stdin,
    output: process.stdout
  }).on('SIGINT', function () {
    process.emit('SIGINT');
  });
}

process.on('SIGINT', () => {
  console.log('SIGINT received (Ctrl+C)');
  cleanup();
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('SIGTERM received');
  cleanup();
  process.exit(0);
});

// Export for testing purposes
module.exports = {
  initializeApp,
  cleanup,
  getAppPaths: () => appPaths,
  isReady: () => isAppReady
};
