/**
 * Database Operations Module
 * Handles SQLite database operations, results management, and export functionality
 */

const { app } = require('electron');
const fs = require('fs');
const path = require('path');
const { resolveDatabasePath } = require('./paths');
const { DATABASE_CONFIG, EXPORT_CONFIG } = require('./config');

/**
 * Get simulation results from a database
 * @param {string} databasePath - Path to the database
 * @param {Object} appPaths - Application paths object
 * @returns {Object} Result object with simulation data
 */
async function getSimulationResults(databasePath, appPaths) {
  try {
    console.log(`[getSimulationResults] Checking database at path: ${databasePath}`);
    
    // Try to resolve the database path
    const resolvedPath = resolveDatabasePath(databasePath, appPaths);
    
    if (!resolvedPath) {
      console.error(`[getSimulationResults] Database not found at any resolved path`);
      
      // If this is a project path, provide additional debugging info
      const isProjectPath = databasePath.startsWith('output/') && databasePath.split('/').length > 2;
      if (isProjectPath) {
        logProjectDirectoryInfo(databasePath, appPaths);
      }
      
      return { success: false, error: 'Database file not found' };
    }
    
    console.log(`[getSimulationResults] Using database at: ${resolvedPath}`);
    
    // Get file stats and basic info
    const stats = fs.statSync(resolvedPath);
    const creationDate = new Date(stats.birthtime).toISOString();
    
    // Try to open the database to verify it's valid and get more info
    const { tableCount, recordCount } = await getDatabaseInfo(resolvedPath);
    
    return {
      success: true,
      data: {
        simulationId: path.basename(resolvedPath, '.db'),
        runDate: creationDate,
        duration: 30, // Default value
        entitiesCount: recordCount || 100, // Use actual count or default
        eventsCount: tableCount || 5,     // Use table count or default
        fileSize: stats.size,
        tableCount: tableCount
      }
    };
  } catch (error) {
    console.error(`[getSimulationResults] Error getting simulation results: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Get database information (table count, record count)
 * @param {string} resolvedPath - Resolved database path
 * @returns {Object} Object with tableCount and recordCount
 */
async function getDatabaseInfo(resolvedPath) {
  const Database = require('better-sqlite3');
  let db = null;
  let tableCount = 0;
  let recordCount = 0;
  
  try {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] [ELECTRON] Opening database connection for getSimulationResults: ${resolvedPath}`);
    
    db = new Database(resolvedPath, { readonly: true });
    console.log(`[${timestamp}] [ELECTRON] Database connection opened successfully for: ${resolvedPath}`);
    
    // Count tables
    const tablesResult = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all();
    tableCount = tablesResult.length;
    
    // Count records in a few key tables if they exist
    const commonTables = ['sim_event_processing', 'Project', 'Consultant', 'Task'];
    for (const table of commonTables) {
      try {
        const count = db.prepare(`SELECT COUNT(*) as count FROM "${table}"`).get();
        if (count) {
          recordCount += count.count;
        }
      } catch (e) {
        // Table might not exist, continue to next table
      }
    }
    
  } catch (dbError) {
    console.error(`[getDatabaseInfo] Error opening database: ${dbError.message}`);
  } finally {
    // ALWAYS close the database connection to prevent EBUSY errors on Windows
    if (db) {
      try {
        const timestamp = new Date().toISOString();
        console.log(`[${timestamp}] [ELECTRON] Closing database connection for getSimulationResults: ${resolvedPath}`);
        db.close();
        console.log(`[${timestamp}] [ELECTRON] Database connection closed successfully for: ${resolvedPath}`);
      } catch (closeError) {
        console.error(`[${timestamp}] [ELECTRON] Error closing database for getSimulationResults: ${closeError.message}`);
      }
    }
  }
  
  return { tableCount, recordCount };
}

/**
 * Get database tables
 * @param {string} databasePath - Path to the database
 * @param {Object} appPaths - Application paths object
 * @returns {Object} Result object with table names
 */
async function getDatabaseTables(databasePath, appPaths) {
  try {
    console.log(`[getDatabaseTables] Getting tables from database at path: ${databasePath}`);
    
    const resolvedPath = resolveDatabasePath(databasePath, appPaths);
    
    if (!resolvedPath) {
      console.error(`[getDatabaseTables] Database not found at any resolved path`);
      
      const isProjectPath = databasePath.startsWith('output/') && databasePath.split('/').length > 2;
      if (isProjectPath) {
        logProjectDirectoryInfo(databasePath, appPaths);
      }
      
      return { success: false, error: 'Database file not found' };
    }
    
    console.log(`[getDatabaseTables] Using database at: ${resolvedPath}`);
    
    // Query for all table names using better-sqlite3
    const Database = require('better-sqlite3');
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] [ELECTRON] Opening database connection for getDatabaseTables: ${resolvedPath}`);
    
    const db = new Database(resolvedPath, { readonly: true });
    console.log(`[${timestamp}] [ELECTRON] Database connection opened successfully for getDatabaseTables: ${resolvedPath}`);
    
    try {
      const rows = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all();
      const tables = rows.map(row => row.name);
      console.log(`[${timestamp}] [ELECTRON] Found ${tables.length} tables: ${tables.join(', ')}`);
      return { success: true, tables };
    } finally {
      console.log(`[${timestamp}] [ELECTRON] Closing database connection for getDatabaseTables: ${resolvedPath}`);
      db.close();
      console.log(`[${timestamp}] [ELECTRON] Database connection closed successfully for getDatabaseTables: ${resolvedPath}`);
    }
  } catch (error) {
    console.error(`[getDatabaseTables] Error getting database tables: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Get table data
 * @param {Object} params - Parameters object
 * @param {Object} appPaths - Application paths object
 * @returns {Object} Result object with table data
 */
async function getTableData(params, appPaths) {
  try {
    const { databasePath, tableName, limit = DATABASE_CONFIG.defaultQueryLimit } = params;
    console.log(`[getTableData] Getting data from table ${tableName} in database at path: ${databasePath}`);
    
    const resolvedPath = resolveDatabasePath(databasePath, appPaths);
    
    if (!resolvedPath) {
      console.error(`[getTableData] Database not found at any resolved path`);
      
      const isProjectPath = databasePath.startsWith('output/') && databasePath.split('/').length > 2;
      if (isProjectPath) {
        logProjectDirectoryInfo(databasePath, appPaths);
      }
      
      return { success: false, error: 'Database file not found' };
    }
    
    console.log(`[getTableData] Using database at: ${resolvedPath} to query table: ${tableName}`);
    
    // Query for table data using better-sqlite3
    const Database = require('better-sqlite3');
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] [ELECTRON] Opening database connection for getTableData: ${resolvedPath}, table: ${tableName}`);
    
    const db = new Database(resolvedPath, { readonly: true });
    console.log(`[${timestamp}] [ELECTRON] Database connection opened successfully for getTableData: ${resolvedPath}`);
    
    try {
      const rows = db.prepare(`SELECT * FROM "${tableName}" LIMIT ${limit}`).all();
      console.log(`[${timestamp}] [ELECTRON] Retrieved ${rows.length} rows from table ${tableName}`);
      return { success: true, data: rows };
    } finally {
      console.log(`[${timestamp}] [ELECTRON] Closing database connection for getTableData: ${resolvedPath}`);
      db.close();
      console.log(`[${timestamp}] [ELECTRON] Database connection closed successfully for getTableData: ${resolvedPath}`);
    }
  } catch (error) {
    console.error(`[getTableData] Error getting table data: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Export database to CSV files
 * @param {string} databasePath - Path to the database
 * @param {string|null} customExportPath - Custom export path or null for default
 * @param {Object} appPaths - Application paths object
 * @returns {Object} Result object with export information
 */
async function exportDatabaseToCSV(databasePath, customExportPath, appPaths) {
  try {
    console.log(`Exporting database at path: ${databasePath} to CSV`);
    if (customExportPath) {
      console.log(`Using custom export path: ${customExportPath}`);
    }
    
    const resolvedPath = resolveDatabasePath(databasePath, appPaths);
    
    if (!resolvedPath) {
      console.error(`Database not found at any resolved path`);
      return { success: false, error: 'Database file not found' };
    }
    
    console.log(`Using database at: ${resolvedPath} for CSV export`);
    
    // Determine export directory
    const exportBaseDir = await getExportDirectory(customExportPath, appPaths);
    if (!exportBaseDir.success) {
      return exportBaseDir;
    }
    
    // Create export subfolder
    const exportDir = await createExportSubfolder(exportBaseDir.path, resolvedPath);
    if (!exportDir.success) {
      return exportDir;
    }
    
    // Export tables to CSV
    const exportResult = await exportTablesToCSV(resolvedPath, exportDir.path);
    
    return {
      success: true,
      exportPath: exportDir.path,
      path: exportDir.path,  // For backward compatibility
      directory: exportBaseDir.path,
      tables: exportResult.tables,
      files: exportResult.files,
      totalRows: exportResult.totalRows
    };
  } catch (error) {
    console.error(`Error exporting database: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Get export directory (custom or default)
 * @param {string|null} customExportPath - Custom export path
 * @param {Object} appPaths - Application paths object
 * @returns {Object} Result with export directory path
 */
async function getExportDirectory(customExportPath, appPaths) {
  if (customExportPath) {
    try {
      // Validate custom path
      if (!fs.existsSync(customExportPath)) {
        fs.mkdirSync(customExportPath, { recursive: true });
        console.log(`Created custom export directory: ${customExportPath}`);
      }
      
      // Test writability
      const testFile = path.join(customExportPath, '.write_test');
      fs.writeFileSync(testFile, 'test');
      fs.unlinkSync(testFile);
      console.log(`Custom export directory is writable: ${customExportPath}`);
      
      return { success: true, path: customExportPath };
    } catch (error) {
      console.error(`Error with custom export directory: ${error.message}`);
      return { success: false, error: `Cannot use selected directory: ${error.message}` };
    }
  } else {
    // Use default exports directory
    const defaultDir = path.join(appPaths.output, EXPORT_CONFIG.defaultExportDir);
    console.log(`Using default export directory at: ${defaultDir}`);
    
    if (!fs.existsSync(defaultDir)) {
      fs.mkdirSync(defaultDir, { recursive: true });
      console.log(`Created default export directory: ${defaultDir}`);
    }
    
    return { success: true, path: defaultDir };
  }
}

/**
 * Create export subfolder with timestamp
 * @param {string} baseDir - Base export directory
 * @param {string} resolvedPath - Resolved database path
 * @returns {Object} Result with subfolder path
 */
async function createExportSubfolder(baseDir, resolvedPath) {
  try {
    const timestamp = new Date().toISOString().replace(EXPORT_CONFIG.timestampFormat, '-');
    const dbName = path.basename(resolvedPath, '.db');
    const exportFolderName = `${dbName}_export_${timestamp}`;
    const exportDir = path.join(baseDir, exportFolderName);
    
    fs.mkdirSync(exportDir, { recursive: true });
    console.log(`Created export subfolder: ${exportDir}`);
    
    return { success: true, path: exportDir };
  } catch (error) {
    console.error(`Error creating export subfolder: ${error.message}`);
    return { success: false, error: `Failed to create export folder: ${error.message}` };
  }
}

/**
 * Export all tables to CSV files
 * @param {string} resolvedPath - Resolved database path
 * @param {string} exportDir - Export directory path
 * @returns {Object} Export results
 */
async function exportTablesToCSV(resolvedPath, exportDir) {
  const Database = require('better-sqlite3');
  let db = null;
  
  try {
    db = new Database(resolvedPath, { readonly: true });
    // Get all tables in the database
    const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all();
    
    if (tables.length === 0) {
      throw new Error('No tables found in database');
    }
    
    console.log(`Found ${tables.length} tables to export: ${tables.map(t => t.name).join(', ')}`);
    
    // Export each table to its own CSV file
    const exportedFiles = [];
    let totalRowsExported = 0;
    
    for (const table of tables) {
      const result = await exportTableToCSV(db, table.name, exportDir);
      exportedFiles.push(result);
      totalRowsExported += result.rows;
    }
    
    // Create summary file
    await createExportSummary(exportDir, exportedFiles, totalRowsExported, path.basename(resolvedPath, '.db'));
    
    console.log(`Successfully exported ${tables.length} tables with ${totalRowsExported} total rows to ${exportDir}`);
    
    return {
      tables: exportedFiles.length,
      files: exportedFiles.map(f => path.basename(f.path)),
      totalRows: totalRowsExported
    };
  } finally {
    if (db) {
      try {
        db.close();
        console.log(`[exportDatabaseToCSV] Database connection closed for: ${resolvedPath}`);
      } catch (closeError) {
        console.error(`[exportDatabaseToCSV] Error closing database: ${closeError.message}`);
      }
    }
  }
}

/**
 * Export a single table to CSV
 * @param {Database} db - Database instance
 * @param {string} tableName - Table name
 * @param {string} exportDir - Export directory
 * @returns {Object} Export result for this table
 */
async function exportTableToCSV(db, tableName, exportDir) {
  console.log(`Exporting table: ${tableName}`);
  
  const tableFileName = `${tableName}.csv`;
  const tableFilePath = path.join(exportDir, tableFileName);
  
  // Get all rows from the table
  const rows = db.prepare(`SELECT * FROM "${tableName}"`).all();
  
  if (rows.length === 0) {
    console.log(`Table ${tableName} has no data, creating empty CSV file`);
    // Create empty file with headers if available
    const columns = getTableColumns(db, tableName);
    fs.writeFileSync(tableFilePath, columns.join(',') + '\n');
    return { table: tableName, path: tableFilePath, rows: 0 };
  }
  
  const headers = Object.keys(rows[0]);
  
  // Write header
  fs.writeFileSync(tableFilePath, headers.join(',') + '\n');
  
  // Write rows in chunks to prevent V8 out-of-memory errors
  const CHUNK_SIZE = 1000;
  for (let i = 0; i < rows.length; i += CHUNK_SIZE) {
    const chunk = rows.slice(i, i + CHUNK_SIZE);
    const chunkContent = chunk.map(row => headers.map(header => {
      const value = row[header];
      if (value === null || value === undefined) return '';
      const str = String(value);
      return str.includes(',') || str.includes('"') || str.includes('\n')
        ? `"${str.replace(/"/g, '""')}"`
        : str;
    }).join(',')).join('\n') + '\n';
    
    fs.appendFileSync(tableFilePath, chunkContent);
  }
  
  console.log(`Exported ${rows.length} rows from table ${tableName} to ${tableFilePath}`);
  
  return { table: tableName, path: tableFilePath, rows: rows.length };
}

/**
 * Get table column names
 * @param {Database} db - Database instance
 * @param {string} tableName - Table name
 * @returns {Array} Array of column names
 */
function getTableColumns(db, tableName) {
  try {
    const columnInfo = db.prepare(`PRAGMA table_info("${tableName}")`).all();
    return columnInfo.map(col => col.name);
  } catch (e) {
    console.error(`Error getting column info for table ${tableName}: ${e.message}`);
    return [];
  }
}

/**
 * Create export summary file
 * @param {string} exportDir - Export directory
 * @param {Array} exportedFiles - Array of exported file info
 * @param {number} totalRowsExported - Total rows exported
 * @param {string} dbName - Database name
 */
async function createExportSummary(exportDir, exportedFiles, totalRowsExported, dbName) {
  const summaryPath = path.join(exportDir, '_summary.json');
  const summary = {
    database: dbName,
    exportedAt: new Date().toISOString(),
    tables: exportedFiles.map(f => ({
      name: f.table,
      rows: f.rows,
      file: path.basename(f.path)
    })),
    totalTables: exportedFiles.length,
    totalRows: totalRowsExported
  };
  
  fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));
}

/**
 * Log project directory information for debugging
 * @param {string} databasePath - Original database path
 * @param {Object} appPaths - Application paths object
 */
function logProjectDirectoryInfo(databasePath, appPaths) {
  const pathParts = databasePath.split('/');
  const projectId = pathParts[1];
  const projectDir = path.join(appPaths.output, projectId);
  
  if (fs.existsSync(projectDir)) {
    console.log(`Project directory exists at: ${projectDir}`);
    console.log(`Contents of project directory:`);
    const files = fs.readdirSync(projectDir);
    files.forEach(file => {
      const filePath = path.join(projectDir, file);
      const stats = fs.statSync(filePath);
      console.log(` - ${file} (${stats.size} bytes)`);
    });
  } else {
    console.log(`Project directory does not exist: ${projectDir}`);
  }
}

module.exports = {
  getSimulationResults,
  getDatabaseTables,
  getTableData,
  exportDatabaseToCSV
};