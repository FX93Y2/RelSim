/**
 * File Operations Module
 * Handles file system operations, directory management, and file validation
 */

const { app, dialog } = require('electron');
const fs = require('fs');
const path = require('path');
const { resolveDatabasePath } = require('./paths');

/**
 * Open and read a file
 * @param {string} filePath - Path to the file
 * @returns {Object} Result object with file content
 */
async function openFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    return { success: true, content };
  } catch (error) {
    console.error(`Error opening file ${filePath}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Save content to a file
 * @param {string} filePath - Path to save the file
 * @param {string} content - Content to write
 * @returns {Object} Result object
 */
async function saveFile(filePath, content) {
  try {
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`Successfully saved file: ${filePath}`);
    return { success: true };
  } catch (error) {
    console.error(`Error saving file ${filePath}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Delete a simulation result file
 * @param {string} resultPath - Path to the result file
 * @param {Object} appPaths - Application paths object
 * @returns {Object} Result object
 */
async function deleteResult(resultPath, appPaths) {
  try {
    console.log(`Deleting simulation result: ${resultPath}`);
    // Resolve the full path to the result file
    const resolvedPath = resolveDatabasePath(resultPath, appPaths);

    if (!resolvedPath) {
      console.error(`Result file not found at any resolved path`);
      return { success: false, error: 'Result file not found' };
    }

    // Add a small delay before deletion to ensure any database connections are closed
    await new Promise(resolve => setTimeout(resolve, 1000));

    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] [ELECTRON] Attempting to delete file: ${resolvedPath}`);

    fs.unlinkSync(resolvedPath);
    console.log(`[${timestamp}] [ELECTRON] Successfully deleted result file: ${resolvedPath}`);

    // Clean up matching per-run log files (<db_name>_YYYYMMDD_HHMMSS.log)
    // in <projectDir>/logs/, with a fallback scan of <projectDir> itself.
    try {
      const dbName = path.basename(resolvedPath, '.db');
      const projectDir = path.dirname(resolvedPath);
      const prefix = `${dbName}_`;

      const dirsToScan = [
        path.join(projectDir, 'logs'),
        projectDir
      ];

      for (const dir of dirsToScan) {
        if (!fs.existsSync(dir)) continue;

        const logFiles = fs.readdirSync(dir).filter(
          f => f.startsWith(prefix) && f.endsWith('.log')
        );

        for (const logFile of logFiles) {
          const logPath = path.join(dir, logFile);
          try {
            fs.unlinkSync(logPath);
            console.log(`[ELECTRON] Deleted run log: ${logPath}`);
          } catch (logErr) {
            console.warn(`[ELECTRON] Could not delete run log ${logPath}: ${logErr.message}`);
          }
        }
      }

      // Remove the logs/ sub-folder if it is now empty
      const logsDir = path.join(projectDir, 'logs');
      if (fs.existsSync(logsDir)) {
        const remaining = fs.readdirSync(logsDir);
        if (remaining.length === 0) {
          fs.rmdirSync(logsDir);
          console.log(`[ELECTRON] Removed empty logs directory: ${logsDir}`);
        }
      }
    } catch (logCleanupErr) {
      // Non-fatal — the DB was already deleted successfully
      console.warn(`[ELECTRON] Error during log cleanup: ${logCleanupErr.message}`);
    }


    return { success: true };
  } catch (error) {
    const timestamp = new Date().toISOString();
    console.error(`[${timestamp}] [ELECTRON] Error deleting result file: ${error.message}`);
    return { success: false, error: error.message };
  }
}


/**
 * Scan for simulation results in a project folder
 * @param {string} projectId - Project ID
 * @param {Object} appPaths - Application paths object
 * @returns {Object} Result object with found results
 */
async function scanProjectResults(projectId, appPaths) {
  try {
    console.log(`Scanning for simulation results in project: ${projectId}`);

    // Determine the output directory for this project using appPaths
    const projectOutputDir = path.join(appPaths.output, projectId);

    console.log(`Checking project output directory: ${projectOutputDir}`);

    // Check if the directory exists
    if (!fs.existsSync(projectOutputDir)) {
      console.log(`Project output directory does not exist: ${projectOutputDir}`);
      return { success: true, results: [] };
    }

    // Get all .db files in the directory
    const files = fs.readdirSync(projectOutputDir)
      .filter(file => file.endsWith('.db'))
      .map(file => {
        const filePath = path.join(projectOutputDir, file);
        const stats = fs.statSync(filePath);

        return {
          id: file.replace('.db', ''),
          name: file.replace('.db', ''),
          path: `output/${projectId}/${file}`,
          size: stats.size,
          created: stats.birthtime
        };
      })
      .sort((a, b) => b.created - a.created); // Sort by creation date, newest first

    console.log(`Found ${files.length} database files in ${projectOutputDir}`);
    if (files.length > 0) {
      console.log(`First result path: ${files[0].path}`);
    }

    return {
      success: true,
      results: files
    };
  } catch (error) {
    console.error(`Error scanning for simulation results: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Show directory picker dialog
 * @param {Object} options - Dialog options
 * @returns {Object} Result object with selected directory
 */
async function showDirectoryPicker(options = {}) {
  try {
    const defaultPath = options.defaultPath || app.getPath('documents');
    const title = options.title || 'Select Export Directory';

    console.log(`Showing directory picker dialog with default path: ${defaultPath}`);

    const result = await dialog.showOpenDialog({
      properties: ['openDirectory', 'createDirectory'],
      defaultPath,
      title,
      buttonLabel: options.buttonLabel || 'Select Folder'
    });

    if (result.canceled) {
      console.log('Directory selection was canceled');
      return { success: false, canceled: true };
    }

    const selectedPath = result.filePaths[0];
    console.log(`Selected directory: ${selectedPath}`);

    // Verify the directory is writable
    const writeTestResult = await testDirectoryWritable(selectedPath);
    if (!writeTestResult.success) {
      return writeTestResult;
    }

    return { success: true, path: selectedPath };
  } catch (error) {
    console.error(`Error showing directory picker: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Test if a directory is writable
 * @param {string} dirPath - Directory path to test
 * @returns {Object} Result object
 */
async function testDirectoryWritable(dirPath) {
  try {
    const testFile = path.join(dirPath, '.write_test');
    fs.writeFileSync(testFile, 'test');
    fs.unlinkSync(testFile);
    console.log(`Directory is writable: ${dirPath}`);
    return { success: true };
  } catch (writeError) {
    console.error(`Directory is not writable: ${writeError.message}`);
    return {
      success: false,
      error: 'Selected directory is not writable. Please choose a different directory.',
      path: dirPath
    };
  }
}

/**
 * Ensure directory exists, create if it doesn't
 * @param {string} dirPath - Directory path
 * @returns {Object} Result object
 */
async function ensureDirectory(dirPath) {
  try {
    if (!fs.existsSync(dirPath)) {
      fs.mkdirSync(dirPath, { recursive: true });
      console.log(`Created directory: ${dirPath}`);
    }
    return { success: true };
  } catch (error) {
    console.error(`Error creating directory ${dirPath}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Get file/directory stats
 * @param {string} filePath - File or directory path
 * @returns {Object} Result object with stats
 */
async function getFileStats(filePath) {
  try {
    const stats = fs.statSync(filePath);
    return {
      success: true,
      stats: {
        size: stats.size,
        created: stats.birthtime,
        modified: stats.mtime,
        isDirectory: stats.isDirectory(),
        isFile: stats.isFile()
      }
    };
  } catch (error) {
    console.error(`Error getting stats for ${filePath}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * List directory contents
 * @param {string} dirPath - Directory path
 * @param {Object} options - Options for filtering
 * @returns {Object} Result object with directory contents
 */
async function listDirectory(dirPath, options = {}) {
  try {
    if (!fs.existsSync(dirPath)) {
      return { success: false, error: 'Directory does not exist' };
    }

    const files = fs.readdirSync(dirPath);

    // Apply filters if specified
    let filteredFiles = files;

    if (options.extension) {
      filteredFiles = filteredFiles.filter(file => file.endsWith(options.extension));
    }

    if (options.includeStats) {
      filteredFiles = filteredFiles.map(file => {
        const filePath = path.join(dirPath, file);
        const stats = fs.statSync(filePath);
        return {
          name: file,
          path: filePath,
          size: stats.size,
          created: stats.birthtime,
          modified: stats.mtime,
          isDirectory: stats.isDirectory(),
          isFile: stats.isFile()
        };
      });
    }

    return { success: true, files: filteredFiles };
  } catch (error) {
    console.error(`Error listing directory ${dirPath}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Copy a file from source to destination
 * @param {string} sourcePath - Source file path
 * @param {string} destPath - Destination file path
 * @returns {Object} Result object
 */
async function copyFile(sourcePath, destPath) {
  try {
    // Ensure destination directory exists
    const destDir = path.dirname(destPath);
    await ensureDirectory(destDir);

    // Copy the file
    fs.copyFileSync(sourcePath, destPath);
    console.log(`Successfully copied file from ${sourcePath} to ${destPath}`);

    return { success: true };
  } catch (error) {
    console.error(`Error copying file from ${sourcePath} to ${destPath}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Move/rename a file
 * @param {string} sourcePath - Source file path
 * @param {string} destPath - Destination file path
 * @returns {Object} Result object
 */
async function moveFile(sourcePath, destPath) {
  try {
    // Ensure destination directory exists
    const destDir = path.dirname(destPath);
    await ensureDirectory(destDir);

    // Move the file
    fs.renameSync(sourcePath, destPath);
    console.log(`Successfully moved file from ${sourcePath} to ${destPath}`);

    return { success: true };
  } catch (error) {
    console.error(`Error moving file from ${sourcePath} to ${destPath}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

module.exports = {
  openFile,
  saveFile,
  deleteResult,
  scanProjectResults,
  showDirectoryPicker,
  testDirectoryWritable,
  ensureDirectory,
  getFileStats,
  listDirectory,
  copyFile,
  moveFile
};