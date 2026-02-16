const { contextBridge, ipcRenderer } = require('electron');

// Node.js globals shim for Monaco editor
contextBridge.exposeInMainWorld('global', {
  // Add any global properties Monaco editor needs
  ArrayBuffer: ArrayBuffer,
  Uint8Array: Uint8Array,
  TextDecoder: TextDecoder,
  TextEncoder: TextEncoder,
  URL: URL,
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: setInterval,
  clearInterval: clearInterval
});

contextBridge.exposeInMainWorld('process', {
  platform: process.platform,
  env: {
    NODE_ENV: process.env.NODE_ENV,
    MONACO_EDITOR_PATH: 'node_modules/monaco-editor/min/vs'
  },
  nextTick: process.nextTick,
  versions: process.versions
});

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld(
  'api', {
  // Project Management
  getProjects: () => ipcRenderer.invoke('api:getProjects'),
  getProject: (projectId) => ipcRenderer.invoke('api:getProject', projectId),
  createProject: (projectData) => ipcRenderer.invoke('api:createProject', projectData),
  updateProject: (projectId, projectData) => ipcRenderer.invoke('api:updateProject', projectId, projectData),
  deleteProject: (projectId) => ipcRenderer.invoke('api:deleteProject', projectId),
  updateProjectOrder: (projectIds) => ipcRenderer.invoke('api:updateProjectOrder', projectIds),

  // Project Configuration Management
  getProjectDbConfig: (projectId) => ipcRenderer.invoke('api:getProjectDbConfig', projectId),
  saveProjectDbConfig: (projectId, configData) => ipcRenderer.invoke('api:saveProjectDbConfig', projectId, configData),
  getProjectSimConfig: (projectId) => ipcRenderer.invoke('api:getProjectSimConfig', projectId),
  saveProjectSimConfig: (projectId, configData) => ipcRenderer.invoke('api:saveProjectSimConfig', projectId, configData),

  // Standalone Configuration Management
  getConfigs: (configType) => ipcRenderer.invoke('api:getConfigs', configType),
  getConfig: (configId) => ipcRenderer.invoke('api:getConfig', configId),
  saveConfig: (configData) => ipcRenderer.invoke('api:saveConfig', configData),
  updateConfig: (configId, configData) => ipcRenderer.invoke('api:updateConfig', configId, configData),
  deleteConfig: (configId) => ipcRenderer.invoke('api:deleteConfig', configId),

  // Database Generation
  generateDatabase: (data) => ipcRenderer.invoke('api:generateDatabase', data),

  // Simulation
  runSimulation: (data) => ipcRenderer.invoke('api:runSimulation', data),
  generateAndSimulate: (data) => ipcRenderer.invoke('api:generateAndSimulate', data),

  // Results Management
  getSimulationResults: (databasePath) => ipcRenderer.invoke('api:getSimulationResults', databasePath),
  getDatabaseTables: (databasePath) => ipcRenderer.invoke('api:getDatabaseTables', databasePath),
  getTableData: (params) => ipcRenderer.invoke('api:getTableData', params),
  exportDatabaseToCSV: (databasePath, customExportPath) => ipcRenderer.invoke('api:exportDatabaseToCSV', databasePath, customExportPath),
  scanProjectResults: (projectId) => ipcRenderer.invoke('api:scanProjectResults', projectId),
  deleteResult: (resultPath) => ipcRenderer.invoke('api:deleteResult', resultPath),

  // File Management
  openFile: (filePath) => ipcRenderer.invoke('api:openFile', filePath),
  saveFile: (filePath, content) => ipcRenderer.invoke('api:saveFile', filePath, content),
  showDirectoryPicker: (options) => ipcRenderer.invoke('api:showDirectoryPicker', options),

  // App Controls
  reloadApp: () => ipcRenderer.invoke('api:reloadApp'),
  closeApp: () => ipcRenderer.invoke('api:closeApp'),
  checkUnsavedChanges: (hasChanges) => ipcRenderer.invoke('api:checkUnsavedChanges', hasChanges),
  openExternalUrl: (url) => ipcRenderer.invoke('api:openExternalUrl', url),
  getAppVersion: () => ipcRenderer.invoke('api:getAppVersion'),

  // App Events
  onAppCloseRequested: (callback) => {
    ipcRenderer.on('app-close-requested', callback);
    // Return cleanup function
    return () => ipcRenderer.removeListener('app-close-requested', callback);
  },

  // Auto-Updater
  checkForUpdate: () => ipcRenderer.invoke('updater:check'),
  openReleasePage: () => ipcRenderer.invoke('updater:open-release-page'),
  onUpdateAvailable: (callback) => {
    ipcRenderer.on('updater:update-available', (_event, info) => callback(info));
    return () => ipcRenderer.removeListener('updater:update-available', callback);
  },
  onUpdateError: (callback) => {
    ipcRenderer.on('updater:error', (_event, error) => callback(error));
    return () => ipcRenderer.removeListener('updater:error', callback);
  }
}
); 