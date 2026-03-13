/**
 * API Handlers Module
 * Contains all IPC handlers for communication between renderer and main processes
 */

const { ipcMain, app, dialog, shell } = require('electron');
const { execFile } = require('child_process');
const os = require('os');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const { API_BASE_URL, CACHE_EXPIRY } = require('./config');
const { waitForBackend } = require('./backend');
const {
  getSimulationResults,
  getDatabaseTables,
  getTableData,
  exportDatabaseToCSV
} = require('./database');
const {
  openFile,
  saveFile,
  deleteResult,
  scanProjectResults,
  showDirectoryPicker
} = require('./file-operations');

// Simple cache for GET requests
const apiCache = {};

/**
 * Register all IPC handlers
 * @param {Object} appPaths - Application paths object
 */
function registerApiHandlers(appPaths) {
  // Project Management
  registerProjectHandlers();

  // Configuration Management
  registerConfigHandlers();

  // Database and Simulation
  registerDatabaseHandlers();

  // Results Management
  registerResultsHandlers(appPaths);

  // File Management
  registerFileHandlers();

  // App Controls
  registerAppControlHandlers();

  console.log('All API handlers registered successfully');
}

/**
 * Register project management handlers
 */
function registerProjectHandlers() {
  ipcMain.handle('api:getProjects', async () => {
    return await makeApiRequest('GET', 'projects');
  });

  ipcMain.handle('api:getProject', async (_, projectId) => {
    return await makeApiRequest('GET', `projects/${projectId}`);
  });

  ipcMain.handle('api:createProject', async (_, projectData) => {
    return await makeApiRequest('POST', 'projects', projectData);
  });

  ipcMain.handle('api:updateProject', async (_, projectId, projectData) => {
    return await makeApiRequest('PUT', `projects/${projectId}`, projectData);
  });

  ipcMain.handle('api:deleteProject', async (_, projectId) => {
    try {
      // First delete the project database entry
      const result = await makeApiRequest('DELETE', `projects/${projectId}`);

      // If successful, also clean up the project's output directory
      if (result.success) {
        await cleanupProjectFiles(projectId);
      }

      return result;
    } catch (error) {
      console.error(`Error deleting project: ${error.message}`);
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('api:updateProjectOrder', async (_, projectIds) => {
    return await makeApiRequest('PUT', 'projects/order', { project_ids: projectIds });
  });
}

/**
 * Register configuration management handlers
 */
function registerConfigHandlers() {
  // Project Configuration Management
  ipcMain.handle('api:getProjectDbConfig', async (_, projectId) => {
    return await makeApiRequest('GET', `projects/${projectId}/db-config`);
  });

  ipcMain.handle('api:saveProjectDbConfig', async (_, projectId, configData) => {
    return await makeApiRequest('POST', `projects/${projectId}/db-config`, configData);
  });

  ipcMain.handle('api:getProjectSimConfig', async (_, projectId) => {
    return await makeApiRequest('GET', `projects/${projectId}/sim-config`);
  });

  ipcMain.handle('api:saveProjectSimConfig', async (_, projectId, configData) => {
    return await makeApiRequest('POST', `projects/${projectId}/sim-config`, configData);
  });

  // Standalone Configuration Management
  ipcMain.handle('api:getConfigs', async (_, configType) => {
    return await makeApiRequest('GET', 'configs', { type: configType });
  });

  ipcMain.handle('api:getConfig', async (_, configId) => {
    return await makeApiRequest('GET', `configs/${configId}`);
  });

  ipcMain.handle('api:saveConfig', async (_, configData) => {
    return await makeApiRequest('POST', 'configs', configData);
  });

  ipcMain.handle('api:updateConfig', async (_, configId, configData) => {
    return await makeApiRequest('PUT', `configs/${configId}`, configData);
  });

  ipcMain.handle('api:deleteConfig', async (_, configId) => {
    return await makeApiRequest('DELETE', `configs/${configId}`);
  });

  ipcMain.handle('api:clearConfigs', async (_, includeProjectConfigs = true) => {
    return await makeApiRequest('POST', 'configs/clear', { include_project_configs: includeProjectConfigs });
  });
}

/**
 * Register database and simulation handlers
 */
function registerDatabaseHandlers() {
  // Database Generation
  ipcMain.handle('api:generateDatabase', async (_, data) => {
    try {
      // Make sure project_id is included in the data for project-specific storage
      if (data.project_id) {
        console.log(`Generating database for project: ${data.project_id}`);
        await ensureProjectDirectory(data.project_id);
      }

      // Pass the request to the backend API
      return await makeApiRequest('POST', 'generate-database', data);
    } catch (error) {
      console.error(`Error generating database: ${error.message}`);
      return { success: false, error: error.message };
    }
  });

  // Simulation
  ipcMain.handle('api:runSimulation', async (_, data) => {
    return await makeApiRequest('POST', 'run-simulation', data);
  });

  ipcMain.handle('api:generateAndSimulate', async (_, data) => {
    return await makeApiRequest('POST', 'generate-and-simulate', data);
  });

  ipcMain.handle('api:simulateWithFormulas', async (_, data) => {
    return await makeApiRequest('POST', 'simulate-with-formulas', data);
  });
}

/**
 * Register results management handlers
 * @param {Object} appPaths - Application paths object
 */
function registerResultsHandlers(appPaths) {
  ipcMain.handle('api:getSimulationResults', async (_, databasePath) => {
    return await getSimulationResults(databasePath, appPaths);
  });

  ipcMain.handle('api:scanProjectResults', async (_, projectId) => {
    return await scanProjectResults(projectId, appPaths);
  });

  ipcMain.handle('api:getDatabaseTables', async (_, databasePath) => {
    return await getDatabaseTables(databasePath, appPaths);
  });

  ipcMain.handle('api:getTableData', async (_, params) => {
    return await getTableData(params, appPaths);
  });

  ipcMain.handle('api:exportDatabaseToCSV', async (_, databasePath, customExportPath) => {
    return await exportDatabaseToCSV(databasePath, customExportPath, appPaths);
  });

  ipcMain.handle('api:deleteResult', async (_, resultPath) => {
    return await deleteResult(resultPath, appPaths);
  });
}

/**
 * Register file management handlers
 */
function registerFileHandlers() {
  ipcMain.handle('api:openFile', async (_, filePath) => {
    return await openFile(filePath);
  });

  ipcMain.handle('api:saveFile', async (_, filePath, content) => {
    return await saveFile(filePath, content);
  });

  ipcMain.handle('api:showDirectoryPicker', async (_, options) => {
    return await showDirectoryPicker(options);
  });

  ipcMain.handle('api:openScriptFolder', async (_, projectId, entityName) => {
    try {
      const { getAppPaths } = require('./paths');
      const appPaths = getAppPaths();

      const projectDir = path.join(appPaths.output, projectId);
      const scriptsDir = path.join(projectDir, 'scripts');

      // Ensure scripts dir exists so the dialog can default to it
      if (!fs.existsSync(scriptsDir)) {
        fs.mkdirSync(scriptsDir, { recursive: true });
        console.log(`Created scripts directory: ${scriptsDir}`);
      }

      // Scaffold a template script for this entity if it doesn't exist yet
      if (entityName) {
        const safeName = entityName.replace(/[^a-zA-Z0-9_]/g, '').toLowerCase();
        const scriptName = `generate_${safeName}.py`;
        const scriptFilePath = path.join(scriptsDir, scriptName);

        if (!fs.existsSync(scriptFilePath)) {
          const templateContent = `"""
Script to generate rows for the '${entityName}' table.
"""

def generate(context):
    """
    Generate Custom Rows

    context.session  - SQLAlchemy session (query parent tables here)
    context.models   - dict of all table models (e.g. context.models['ParentTable'])
    context.entity   - the entity configuration
    context.logger   - logger instance (appears in app logs)

    Returns:
        List[dict]: A list of dictionaries representing the rows to insert.
    """

    context.logger.info("Generating rows for ${entityName}...")

    rows = []

    # --- Example ---
    # rows.append({
    #     "id": "123",
    #     "name": "Sample",
    #     # any columns defined in the YAML config
    # })

    return rows
`;
          fs.writeFileSync(scriptFilePath, templateContent, 'utf-8');
          console.log(`Created script template: ${scriptFilePath}`);
        }
      }

      // Use Electron's native file dialog (works on all platforms including WSL)
      const result = await dialog.showOpenDialog({
        title: 'Select Python Script',
        defaultPath: scriptsDir,
        filters: [{ name: 'Python Scripts', extensions: ['py'] }],
        properties: ['openFile']
      });

      if (result.canceled) {
        return { success: false, canceled: true };
      }

      return { success: true, path: result.filePaths[0] };

    } catch (error) {
      console.error(`Error opening script picker: ${error.message}`);
      return { success: false, error: error.message };
    }
  });
}

/**
 * Helper function to make API requests
 * @param {string} method - HTTP method
 * @param {string} endpoint - API endpoint
 * @param {Object} data - Request data
 * @returns {Object} API response
 */
async function makeApiRequest(method, endpoint, data = null) {
  try {
    // Make sure backend is up and running
    await waitForBackend();

    const url = `${API_BASE_URL}/${endpoint}`;
    let response;

    // For GET requests, check the cache first
    if (method === 'GET') {
      const cacheKey = `${method}:${url}:${JSON.stringify(data || {})}`;
      const cachedResponse = apiCache[cacheKey];

      if (cachedResponse && Date.now() - cachedResponse.timestamp < CACHE_EXPIRY) {
        // Only log cache hits in development when debugging
        if (process.env.NODE_ENV === 'development' && process.env.DEBUG_CACHE) {
          console.log(`Using cached response for ${method} ${url}`);
        }
        return cachedResponse.data;
      }

      response = await axios.get(url, { params: data });

      // Cache the response
      apiCache[cacheKey] = {
        data: response.data,
        timestamp: Date.now()
      };
    } else if (method === 'POST') {
      response = await axios.post(url, data);
      // Invalidate GET caches for this endpoint
      invalidateCache(endpoint);
    } else if (method === 'PUT') {
      response = await axios.put(url, data);
      // Invalidate GET caches for this endpoint
      invalidateCache(endpoint);
    } else if (method === 'DELETE') {
      response = await axios.delete(url, { data });
      // Invalidate all caches
      clearCache();
    }

    return response.data;
  } catch (error) {
    console.error(`API ${method} request to ${endpoint} failed:`, error.message);

    // Check if backend is not running
    if (error.code === 'ECONNREFUSED') {
      console.error('Backend API is not running. Please ensure the Python backend is started.');
      return {
        success: false,
        error: 'Backend API is not available. The application backend may not be running.',
        errorCode: 'BACKEND_UNAVAILABLE'
      };
    }

    // Check for network errors
    if (error.code === 'ENETUNREACH' || error.code === 'ETIMEDOUT') {
      return {
        success: false,
        error: 'Network error: Unable to reach the backend API',
        errorCode: 'NETWORK_ERROR'
      };
    }

    // Handle HTTP response errors
    if (error.response) {
      return {
        success: false,
        error: error.response.data?.error || `API request failed with status ${error.response.status}`,
        errorCode: 'API_ERROR',
        statusCode: error.response.status
      };
    }

    // Generic error
    return {
      success: false,
      error: error.message || 'API request failed',
      errorCode: 'UNKNOWN_ERROR'
    };
  }
}

/**
 * Invalidate cache entries for a specific endpoint
 * @param {string} endpoint - Endpoint to invalidate
 */
function invalidateCache(endpoint) {
  Object.keys(apiCache).forEach(key => {
    if (key.includes(endpoint)) {
      delete apiCache[key];
    }
  });
}

/**
 * Clear all cache entries
 */
function clearCache() {
  Object.keys(apiCache).forEach(key => {
    delete apiCache[key];
  });
}

/**
 * Clean up project files when deleting a project
 * @param {string} projectId - Project ID
 */
async function cleanupProjectFiles(projectId) {
  try {
    // Build the path to the project's output directory
    const projectOutputDir = path.resolve(path.dirname(app.getAppPath()), 'output', projectId);

    // Check if the directory exists
    if (fs.existsSync(projectOutputDir)) {
      console.log(`Cleaning up project output directory: ${projectOutputDir}`);

      // Get all files in the directory
      const files = fs.readdirSync(projectOutputDir);

      // Delete each file
      for (const file of files) {
        const filePath = path.join(projectOutputDir, file);
        fs.unlinkSync(filePath);
        console.log(`Deleted file: ${filePath}`);
      }

      // Delete the directory itself
      fs.rmdirSync(projectOutputDir);
      console.log(`Deleted project output directory: ${projectOutputDir}`);
    }
  } catch (cleanupError) {
    console.error(`Error cleaning up project files: ${cleanupError.message}`);
    // Don't fail the operation if cleanup fails
  }
}

/**
 * Ensure project directory exists for database generation
 * @param {string} projectId - Project ID
 */
async function ensureProjectDirectory(projectId) {
  const { getAppPaths } = require('./paths');
  const appPaths = getAppPaths();

  if (app.isPackaged) {
    const projectDir = path.join(appPaths.output, projectId);
    if (!fs.existsSync(projectDir)) {
      fs.mkdirSync(projectDir, { recursive: true });
      console.log(`Created project output directory: ${projectDir}`);
    }
  }
}

/**
 * Register app control handlers
 */
function registerAppControlHandlers() {
  const { getMainWindow } = require('./window');

  ipcMain.handle('api:reloadApp', async () => {
    const mainWindow = getMainWindow();
    if (mainWindow) {
      mainWindow.webContents.reload();
      return { success: true };
    }
    return { success: false, error: 'Main window not found' };
  });

  ipcMain.handle('api:getAppVersion', async () => {
    return { success: true, version: app.getVersion() };
  });

  ipcMain.handle('api:closeApp', async () => {
    const mainWindow = getMainWindow();
    if (mainWindow) {
      // Force close by removing the close event listener temporarily
      mainWindow.removeAllListeners('close');
      mainWindow.close();
    } else {
      app.quit();
    }
    return { success: true };
  });

  ipcMain.handle('api:checkUnsavedChanges', async (_, hasChanges) => {
    // This can be used to store unsaved changes state in main process if needed
    return { success: true, hasUnsavedChanges: hasChanges };
  });

  ipcMain.handle('api:openExternalUrl', async (_, url) => {
    try {
      // Validate URL format
      const urlObj = new URL(url);

      // Allow only HTTPS URLs to trusted documentation domains
      const allowedDomains = [
        'fakerjs.dev',
        'docs.python.org',
        'numpy.org',
        'pandas.pydata.org',
        'matplotlib.org',
        'seaborn.pydata.org',
        'plotly.com',
        'github.com',
        'stackoverflow.com',
        'developer.mozilla.org'
      ];

      if (urlObj.protocol !== 'https:') {
        return { success: false, error: 'Only HTTPS URLs are allowed' };
      }

      const isAllowedDomain = allowedDomains.some(domain =>
        urlObj.hostname === domain || urlObj.hostname.endsWith('.' + domain)
      );

      if (!isAllowedDomain) {
        return { success: false, error: 'URL domain not in allowed list' };
      }

      // Open URL: handle WSL explicitly to avoid xdg-open failures
      const isWSL = process.platform === 'linux' && (
        process.env.WSL_DISTRO_NAME || os.release().toLowerCase().includes('microsoft')
      );

      if (isWSL) {
        // Prefer wslview when available (opens in Windows default browser)
        const tryExec = (cmd, args) => new Promise((resolve, reject) => {
          const child = execFile(cmd, args, (err) => err ? reject(err) : resolve());
          // In case the process cannot spawn at all (ENOENT), handle via callback
          child.on('error', reject);
        });

        try {
          await tryExec('wslview', [url]);
          return { success: true };
        } catch (e1) {
          try {
            // Fallback: use Windows cmd to start default browser
            await tryExec('cmd.exe', ['/c', 'start', '', url]);
            return { success: true };
          } catch (e2) {
            // Final fallback to Electron shell; may still fail if xdg-open missing
            await shell.openExternal(url);
            return { success: true };
          }
        }
      }

      // Non-WSL: open in user's default browser
      await shell.openExternal(url);
      return { success: true };

    } catch (error) {
      console.error('Error opening external URL:', error);
      return { success: false, error: error.message };
    }
  });
}

/**
 * Get API cache statistics
 * @returns {Object} Cache statistics
 */
function getCacheStats() {
  const entries = Object.keys(apiCache).length;
  const totalSize = JSON.stringify(apiCache).length;

  return {
    entries,
    totalSize,
    expiry: CACHE_EXPIRY
  };
}

module.exports = {
  registerApiHandlers,
  makeApiRequest,
  invalidateCache,
  clearCache,
  getCacheStats
};
