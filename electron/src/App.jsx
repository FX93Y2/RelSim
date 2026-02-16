import React, { useState, useEffect, useRef } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Container } from 'react-bootstrap';

// Layout Components
import Header from './components/layout/Header';
import ProjectSidebar from './components/layout/Sidebar';
import NavigationSidebar from './components/layout/NavigationSidebar';
import GuideOverlay from './components/shared/GuideOverlay';
import UpdateNotification from './components/shared/UpdateNotification';

// Pages
import ConfigurationGuide from './components/pages/ConfigurationGuide';
import ProjectPage from './components/pages/ProjectPage';
import DbConfigEditor from './components/pages/DbConfigEditor';
import SimConfigEditor from './components/pages/SimConfigEditor';
import ResultsViewer from './components/pages/ResultsViewer';

// Toast Context
import { ToastProvider } from './contexts/ToastContext';
import { DndProvider } from './contexts/DndContext';
import useResizableGrid from './hooks/shared/useResizableGrid';

const App = () => {
  // Theme state management - initialize from localStorage or default to 'dark'
  const [theme, setTheme] = useState(() => {
    const savedTheme = localStorage.getItem('theme');
    return savedTheme || 'dark';
  });

  // Effect to apply theme class to body
  useEffect(() => {
    // Remove any conflicting theme classes
    document.body.classList.remove('theme-light', 'theme-dark');
    document.body.classList.add(`theme-${theme}`);

    // Keep body overflow hidden for app-like behavior
    document.body.style.overflow = 'hidden';

    // Save theme preference to localStorage
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Signal when React is ready to help with loading screen transition
  useEffect(() => {
    const timer = setTimeout(() => {
      // Signal that React app is fully rendered
      document.body.classList.add('react-ready');

      // Use the global function to hide loading screen
      if (window.hideLoadingScreen) {
        window.hideLoadingScreen();
      }
    }, 500); // Small delay to ensure content is rendered

    return () => clearTimeout(timer);
  }, []);

  // Ensure the app can always close via system close button
  // If no page-level unsaved-changes handler is active, close immediately.
  useEffect(() => {
    if (!window.api?.onAppCloseRequested) return;
    const cleanup = window.api.onAppCloseRequested(() => {
      const hasUnsaved = window.__unsavedChangesState?.hasUnsavedChanges;
      if (!hasUnsaved) {
        window.api?.closeApp?.();
      }
      // If there are unsaved changes, ProjectPage listener will handle the modal
    });
    return cleanup;
  }, []);

  // Function to toggle theme
  const toggleTheme = () => {
    setTheme((prevTheme) => (prevTheme === 'light' ? 'dark' : 'light'));
  };

  // Sidebar state management (supports multiple sidebar types)
  const [sidebarMode, setSidebarMode] = useState(() => {
    const savedMode = localStorage.getItem('sidebarMode');
    return savedMode || 'database'; // 'database', 'navigation', or 'none'
  });

  const [sidebarVisible, setSidebarVisible] = useState(() => {
    const savedVisibility = localStorage.getItem('sidebarVisible');
    return savedVisibility !== null ? savedVisibility === 'true' : true;
  });

  // Save sidebar state to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('sidebarVisible', sidebarVisible.toString());
    localStorage.setItem('sidebarMode', sidebarMode);
  }, [sidebarVisible, sidebarMode]);

  // Toggle sidebar visibility (main toggle)
  const toggleSidebar = () => {
    setSidebarVisible(prev => !prev);
  };

  // Toggle navigation sidebar (for help/guide)
  const toggleNavigationSidebar = () => {
    if (sidebarMode === 'navigation' && sidebarVisible) {
      // If navigation sidebar is open, close it
      setSidebarVisible(false);
    } else {
      // Switch to navigation mode and ensure sidebar is visible
      setSidebarMode('navigation');
      setSidebarVisible(true);
    }
  };

  // Toggle database explorer (enhanced to properly handle both open and close)
  const toggleDatabaseExplorer = () => {
    if (sidebarMode === 'database' && sidebarVisible) {
      // If database explorer is open, close sidebar
      setSidebarVisible(false);
    } else {
      // Switch to database mode and ensure sidebar is visible
      setSidebarMode('database');
      setSidebarVisible(true);
    }
  };

  // Guide overlay state
  const [guideOverlayVisible, setGuideOverlayVisible] = useState(false);
  const [activeGuideSection, setActiveGuideSection] = useState('database-configuration');

  // Handle guide section selection from navigation sidebar
  const handleGuideSectionSelect = (sectionId) => {
    setActiveGuideSection(sectionId);
    setGuideOverlayVisible(true);
  };

  // Close guide overlay
  const closeGuideOverlay = () => {
    setGuideOverlayVisible(false);
  };

  // Sidebar resize functionality
  const { handleMouseDown: handleSidebarResize } = useResizableGrid({
    minWidthPercent: 10,
    maxWidthPercent: 40,
    defaultWidthPercent: 15,
    cssVariable: '--sidebar-width',
    storageKey: 'app-sidebar-width'
  });

  return (
    <ToastProvider>
      <DndProvider theme={theme}>
        <div className={`app-grid-container ${!sidebarVisible ? 'sidebar-collapsed' : ''}`}>
          {/* Header Panel */}
          <div className="grid-header">
            <Header
              currentTheme={theme}
              onToggleTheme={toggleTheme}
              sidebarVisible={sidebarVisible}
              sidebarMode={sidebarMode}
              onToggleSidebar={toggleDatabaseExplorer}
              onToggleNavigationSidebar={toggleNavigationSidebar}
            />
          </div>

          {/* Sidebar Panel */}
          <div className="grid-sidebar">
            {sidebarMode === 'database' ? (
              <ProjectSidebar theme={theme} visible={sidebarVisible} />
            ) : (
              <NavigationSidebar
                theme={theme}
                visible={sidebarVisible}
                onSectionSelect={handleGuideSectionSelect}
                activeSection={activeGuideSection}
              />
            )}
          </div>

          {/* Sidebar Resize Handle */}
          {sidebarVisible && (
            <div
              className="grid-sidebar-handle"
              onMouseDown={handleSidebarResize}
              title="Drag to resize sidebar"
            />
          )}

          {/* Content Panel */}
          <div className="grid-content">
            <div className="content-area">
              <Container fluid className="p-0 h-100">
                <Routes>
                  {/* Welcome and dashboard */}
                  <Route path="/" element={<ConfigurationGuide />} />

                  {/* Project routes */}
                  <Route path="/project/:projectId" element={<ProjectPage theme={theme} />} />
                  <Route path="/project/:projectId/:activeTab" element={<ProjectPage theme={theme} />} />
                  <Route path="/project/:projectId/results/:resultId" element={<ProjectPage theme={theme} />} />

                  {/* Standalone configuration routes */}
                  <Route path="/db-config" element={<DbConfigEditor theme={theme} />} />
                  <Route path="/db-config/:configId" element={<DbConfigEditor theme={theme} />} />
                  <Route path="/sim-config" element={<SimConfigEditor theme={theme} />} />
                  <Route path="/sim-config/:configId" element={<SimConfigEditor theme={theme} />} />

                  {/* Results routes */}
                  <Route path="/results/:databasePath" element={<ResultsViewer />} />

                  {/* Default catch-all route */}
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Container>
            </div>
          </div>

          {/* Guide Overlay */}
          <GuideOverlay
            visible={guideOverlayVisible}
            activeSection={activeGuideSection}
            onClose={closeGuideOverlay}
          />

          {/* Update Notification */}
          <UpdateNotification />
        </div>
      </DndProvider>
    </ToastProvider>
  );
};

export default App; 
