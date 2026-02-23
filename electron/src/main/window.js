/**
 * Window Management Module
 * Handles window creation, configuration, and event management
 */

const { app, BrowserWindow, Menu } = require('electron');
const path = require('path');
const { WINDOW_CONFIG, CSP_HEADER } = require('./config');

let mainWindow = null;

/**
 * Create the main application window
 * @param {string} preloadPath - Path to the preload script
 * @returns {BrowserWindow} The created window instance
 */
function createWindow(preloadPath) {
  // Update preload path in config
  const windowConfig = {
    ...WINDOW_CONFIG,
    title: `RelSim v${app.getVersion()}`,
    webPreferences: {
      ...WINDOW_CONFIG.webPreferences,
      preload: preloadPath
    }
  };

  // Create the browser window
  mainWindow = new BrowserWindow(windowConfig);

  // Remove the default application menu
  mainWindow.setMenu(null);

  // Set up Content Security Policy
  setupCSP();

  // Set up context menu
  setupContextMenu();

  // Show window when ready to prevent flash
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Load the index.html file
  mainWindow.loadFile(path.join(__dirname, '..', '..', 'index.html'));

  // Handle window close event (before closing)
  mainWindow.on('close', (event) => {
    // Always prevent immediate close and let renderer handle unsaved changes
    event.preventDefault();

    // Send close request to renderer
    mainWindow.webContents.send('app-close-requested');
  });

  // Handle window closed event (after closing)
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  return mainWindow;
}

/**
 * Set up Content Security Policy for the window
 */
function setupCSP() {
  mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [CSP_HEADER]
      }
    });
  });
}

/**
 * Set up context menu with different options for development and production
 */
function setupContextMenu() {
  const { app } = require('electron');

  mainWindow.webContents.on('context-menu', (event, params) => {
    let template;

    if (app.isPackaged) {
      // Production menu - essential options for end users
      template = [
        {
          label: 'Reload',
          click: () => {
            mainWindow.webContents.reload();
          }
        },
        { type: 'separator' },
        {
          label: 'Inspect Element',
          click: () => {
            mainWindow.webContents.openDevTools({ mode: 'detach' });
          }
        }
      ];
    } else {
      // Development menu - full debugging options
      template = [
        {
          label: 'Inspect Element',
          click: () => {
            mainWindow.webContents.openDevTools({ mode: 'detach' });
          }
        },
        { type: 'separator' },
        {
          label: 'Reload',
          click: () => {
            mainWindow.webContents.reload();
          }
        },
        {
          label: 'Force Reload',
          click: () => {
            mainWindow.webContents.reloadIgnoringCache();
          }
        }
      ];
    }

    const menu = Menu.buildFromTemplate(template);
    menu.popup({ window: mainWindow, x: params.x, y: params.y });
  });
}

/**
 * Get the main window instance
 * @returns {BrowserWindow|null} The main window instance or null
 */
function getMainWindow() {
  return mainWindow;
}

/**
 * Check if the main window exists and is not destroyed
 * @returns {boolean} True if window exists and is not destroyed
 */
function isWindowReady() {
  return mainWindow && !mainWindow.isDestroyed();
}

/**
 * Close the main window
 */
function closeWindow() {
  if (mainWindow) {
    mainWindow.close();
  }
}

/**
 * Show the main window
 */
function showWindow() {
  if (mainWindow) {
    mainWindow.show();
  }
}

/**
 * Hide the main window
 */
function hideWindow() {
  if (mainWindow) {
    mainWindow.hide();
  }
}

/**
 * Focus the main window
 */
function focusWindow() {
  if (mainWindow) {
    mainWindow.focus();
  }
}

module.exports = {
  createWindow,
  getMainWindow,
  isWindowReady,
  closeWindow,
  showWindow,
  hideWindow,
  focusWindow
};