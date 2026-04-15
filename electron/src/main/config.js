/**
 * Application Configuration Module
 * Centralized configuration and constants for the Electron main process
 */

// API Configuration
const API_BASE_URL = 'http://127.0.0.1:5001/api';

// Cache Configuration
const CACHE_EXPIRY = 10000; // 10 seconds in ms

// Window Configuration
const WINDOW_CONFIG = {
  width: 1200,
  height: 800,
  backgroundColor: '#1a1a1a', // Dark theme background to prevent white flash
  show: false, // Don't show until ready-to-show event
  webPreferences: {
    nodeIntegration: false,
    contextIsolation: true,
    preload: null // Will be set dynamically
  }
};

// Content Security Policy
const CSP_HEADER = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdn.jsdelivr.net/npm/* https://unpkg.com/*",
  "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.jsdelivr.net/npm/* https://unpkg.com/*",
  "font-src 'self' https://cdn.jsdelivr.net https://cdn.jsdelivr.net/npm/* https://unpkg.com/*",
  "img-src 'self' data: blob:",
  "connect-src 'self' http://localhost:* http://127.0.0.1:*",
  "worker-src 'self' blob:"
].join('; ');

// Backend Configuration
const BACKEND_CONFIG = {
  maxStartupTries: 30,
  retryDelay: 1000, // 1 second
  maxRetries: 3,
  retryDelayMs: 300
};

// Database Configuration
const DATABASE_CONFIG = {
  defaultQueryLimit: 1000,
  connectionTimeout: 1000,
  maxRetries: 3
};

// Export Configuration
const EXPORT_CONFIG = {
  defaultExportDir: 'exports',
  timestampFormat: /[:.]/g, // Regex for timestamp formatting
  maxCsvRows: 100000 // Safety limit for CSV exports
};

module.exports = {
  API_BASE_URL,
  CACHE_EXPIRY,
  WINDOW_CONFIG,
  CSP_HEADER,
  BACKEND_CONFIG,
  DATABASE_CONFIG,
  EXPORT_CONFIG
};