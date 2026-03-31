import React, { useState, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { Button, Modal } from 'react-bootstrap';
import ModularEventFlow from '../simulation/ModularEventFlow';
import SimulationResourceEditor from '../simulation/simulation_data_editors/SimulationResourceEditor';
import SimulationEntityEditor from '../simulation/simulation_data_editors/SimulationEntityEditor';
import SimulationQueueEditor from '../simulation/simulation_data_editors/SimulationQueueEditor';
import SimulationSettingsEditor from '../simulation/simulation_data_editors/SimulationSettingsEditor';
import FloatingToolbar from '../shared/FloatingToolbar';
import SimConfigYamlPanel from '../simulation/SimConfigYamlPanel';
import EditorHeader from '../shared/EditorHeader';
import EditorLayout from '../shared/EditorLayout';
import { useToastContext } from '../../contexts/ToastContext';
import useResizableGrid from '../../hooks/shared/useResizableGrid';
import useYamlOperations from '../../hooks/shared/useYamlOperations';
import useExportAllConfigs from '../../hooks/shared/useExportAllConfigs';
import useKeyboardShortcuts from '../../hooks/shared/useKeyboardShortcuts';
import useConfigurationLoader from '../../hooks/shared/useConfigurationLoader';
import useResourceDefinitions from '../../hooks/shared/useResourceDefinitions';
import { getSimToolbarItems } from '../../config/toolbars/simToolbarConfig';
import RunSimulationModal from '../modals/RunSimulationModal';

// New store imports
import {
  useSimulationConfigStore,
  useYamlContent,
  useParsedSchema,
  useCanonicalSteps,
  useIsLoading,
  useError,
  useSimulationSelectionMode,
  useYamlActions,
  useCanvasActions,
  useConfigActions,
  useSimulationActions,
  useUIActions
} from '../../stores/simulationConfigStore';

// Database store imports (for Export All feature)
import { useDatabaseYamlContent } from '../../stores/databaseConfigStore';

const SimConfigEditor = ({
  projectId,
  isProjectTab,
  theme,
  currentTab,
  onTabChange,
  dbConfigContent,
  onConfigChange,
  onSaveSuccess,
  onSaveAll = null
}) => {
  const { configId } = useParams();
  const { showError } = useToastContext();

  // Resizable grid hook for panel sizing - unified across both editors
  const { handleMouseDown } = useResizableGrid({
    minWidthPercent: 22,
    maxWidthPercent: 60,
    defaultWidthPercent: 20,
    cssVariable: '--yaml-panel-width',
    storageKey: 'unified-yaml-panel-width'
  });

  // Store state subscriptions
  const yamlContent = useYamlContent(projectId);
  const dbYamlContent = useDatabaseYamlContent(projectId);
  const parsedSchema = useParsedSchema(projectId);
  const canonicalSteps = useCanonicalSteps(projectId);
  const isLoading = useIsLoading(projectId);
  const error = useError(projectId);
  const selectionMode = useSimulationSelectionMode(projectId);

  // Store actions
  const { importYaml, updateYamlContent } = useYamlActions(projectId);
  const { addNode } = useCanvasActions(projectId);
  const { loadConfig, saveConfig, initializeConfig, hasContent, undo, redo, canUndo, canRedo } = useConfigActions(projectId);
  const { syncSimulationToYaml, updateResourceCapacity, clearAllResources, getEffectiveSimulationData, removeResource } = useSimulationActions(projectId);
  const { toggleSelectionMode } = useUIActions(projectId);

  // Resource definitions from database config
  const resourceDefinitions = useResourceDefinitions(dbConfigContent);

  // Local modal state
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [showRunModal, setShowRunModal] = useState(false);
  const [showResourceModal, setShowResourceModal] = useState(false);
  const [showEntityModal, setShowEntityModal] = useState(false);
  const [showQueueModal, setShowQueueModal] = useState(false);
  const [showSimulationModal, setShowSimulationModal] = useState(false);

  // Get project/config name from store for export filename
  const configName = useSimulationConfigStore(projectId)(state => state.name);

  // Custom hooks for shared functionality
  const yamlOperations = useYamlOperations({
    yamlContent,
    onImport: importYaml,
    filename: 'simulation-config',
    saveConfig,
    isProjectTab,
    projectId,
    configType: 'simulation'
  });

  const { handleExportAll } = useExportAllConfigs({
    projectName: configName || 'project',
    dbYamlContent: dbYamlContent,
    simYamlContent: yamlContent
  });

  useKeyboardShortcuts({ undo, redo, canUndo, canRedo });

  useConfigurationLoader({
    projectId,
    configId,
    isProjectTab,
    theme,
    onConfigChange,
    yamlContent,
    error,
    initializeConfig,
    loadConfig,
    hasContent
  });

  const [configLoaded, setConfigLoaded] = useState(false);

  // Mark config as loaded once yamlContent becomes available and we're not loading
  React.useEffect(() => {
    if (!isLoading && yamlContent && !configLoaded) {
      setConfigLoaded(true);
    }
  }, [isLoading, yamlContent, configLoaded]);

  // Resource synchronization - auto-manage resources when database config changes
  React.useEffect(() => {
    // Wait until the simulation config has actually been loaded from backend
    // isLoading starts as false, so we can't rely on it alone - we need configLoaded
    if (!isLoading && dbConfigContent && configLoaded && Object.keys(resourceDefinitions).length >= 0) {
      console.log('[SimConfigEditor] Resource definitions detected:', Object.keys(resourceDefinitions));

      const currentSimulationData = getEffectiveSimulationData();
      const currentResources = currentSimulationData.resources || [];

      // Get all current resource table names
      const currentResourceTables = new Set(currentResources.map(r => r.resource_table));

      // Get all detected resource table names
      const detectedResourceTables = new Set(Object.keys(resourceDefinitions));

      let hasChanges = false;

      // Add new resources that don't exist in current simulation data
      Object.keys(resourceDefinitions).forEach(resourceName => {
        const definition = resourceDefinitions[resourceName];
        const existingResource = currentResources.find(r => r.resource_table === resourceName);

        if (!existingResource) {
          console.log(`[SimConfigEditor] Adding new resource table: ${resourceName}`);
          definition.resourceTypes.forEach(resourceType => {
            updateResourceCapacity(resourceName, resourceType, 1);
            hasChanges = true;
          });
        } else {
          // Check for new resource types within existing resource table
          definition.resourceTypes.forEach(resourceType => {
            if (!existingResource.capacities?.[resourceType]) {
              console.log(`[SimConfigEditor] Adding new resource type: ${resourceName}.${resourceType}`);
              updateResourceCapacity(resourceName, resourceType, 1);
              hasChanges = true;
            }
          });
        }
      });

      // Remove resources that no longer exist in database config
      currentResourceTables.forEach(resourceTable => {
        if (!detectedResourceTables.has(resourceTable)) {
          console.log(`[SimConfigEditor] Removing deleted resource table: ${resourceTable}`);
          removeResource(resourceTable);
          hasChanges = true;
        }
      });

      // If no resources detected, clear all resources
      if (Object.keys(resourceDefinitions).length === 0 && currentResources.length > 0) {
        console.log('[SimConfigEditor] No resources detected, clearing all');
        clearAllResources();
        hasChanges = true;
      }

      // Sync to YAML if changes were made
      if (hasChanges) {
        setTimeout(() => {
          syncSimulationToYaml();
        }, 100); // Small delay to ensure all store updates are complete
      }
    }
  }, [dbConfigContent, resourceDefinitions, isLoading, configLoaded, updateResourceCapacity, clearAllResources, getEffectiveSimulationData, removeResource, syncSimulationToYaml]);

  // Generate collision-free step ID
  const generateStepId = useCallback((stepType) => {
    const existingStepIds = canonicalSteps.map(s => s.step_id);

    if (stepType === 'create') {
      let counter = 1;
      let stepId = `create_entities_${counter}`;
      while (existingStepIds.includes(stepId)) {
        counter++;
        stepId = `create_entities_${counter}`;
      }
      return stepId;
    }

    let counter = 1;
    let stepId = `${stepType}_${counter}`;
    while (existingStepIds.includes(stepId)) {
      counter++;
      stepId = `${stepType}_${counter}`;
    }

    return stepId;
  }, [canonicalSteps]);

  // Add module handler
  const handleAddModule = useCallback((moduleType) => {
    if (!parsedSchema) {
      showError('Configure Simulation Duration First!');
      return;
    }

    const stepId = generateStepId(moduleType);
    const position = {
      x: 50 + (canonicalSteps.length % 3) * 300,
      y: 100 + Math.floor(canonicalSteps.length / 3) * 200
    };

    // Create step based on type
    let newStep = {
      step_id: stepId,
      step_type: moduleType
    };

    switch (moduleType) {
      case 'event':
        newStep.event_config = {
          duration: { distribution: { type: "normal", mean: 5, stddev: 1 } },
          resource_requirements: []
        };
        newStep.next_steps = [];
        break;
      case 'decide':
        newStep.decide_config = {
          decision_type: "2way-chance",
          outcomes: [
            {
              outcome_id: "outcome_1",
              next_step_id: "",
              conditions: [{ if: "Probability", is: "==", value: 0.5 }]
            },
            {
              outcome_id: "outcome_2",
              next_step_id: "",
              conditions: [{ if: "Probability", is: "==", value: 0.5 }]
            }
          ]
        };
        break;
      case 'assign':
        newStep.assign_config = {
          assignments: [{
            assignment_type: "attribute",
            attribute_name: "new_attribute",
            value: "default_value"
          }]
        };
        newStep.next_steps = [];
        break;
      case 'release':
        // Release modules don't need event_config
        break;
      case 'create':
        newStep.create_config = {
          entity_table: "",
          interarrival_time: {
            distribution: {
              type: "exponential",
              scale: 2
            }
          },
          max_entities: "n/a"
        };
        break;
      default:
        console.warn('Unknown module type:', moduleType);
        return;
    }

    // Add to store
    addNode(newStep, position);
    console.log('➕ SimConfigEditor: Added module:', stepId);
  }, [parsedSchema, canonicalSteps, generateStepId, addNode, showError]);

  // Save handler
  const handleSave = useCallback(async () => {
    console.log('💾 SimConfigEditor: Save requested');

    if (projectId && isProjectTab && onSaveAll) {
      // Use unified save function for project tabs when available
      onSaveAll();
    } else if (projectId && isProjectTab) {
      // Save directly for project tabs
      const result = await saveConfig();
      if (result.success && onSaveSuccess) {
        onSaveSuccess();
      }
    } else {
      // Show save modal for standalone configs
      setShowSaveModal(true);
    }
  }, [projectId, isProjectTab, saveConfig, onSaveSuccess, onSaveAll]);



  // Handle configuration modal opening
  const handleConfigOpen = useCallback((configType) => {
    if (configType === 'resource') {
      setShowResourceModal(true);
    } else if (configType === 'entity') {
      setShowEntityModal(true);
    } else if (configType === 'queue') {
      setShowQueueModal(true);
    }
  }, []);


  // Get toolbar configuration
  const toolbarItems = getSimToolbarItems({
    setShowSimulationModal,
    setShowRunModal,
    toggleSelectionMode,
    selectionMode,
    undo,
    redo,
    canUndo,
    canRedo,
    isLoading
  });

  // CSS Grid-based editor component (VS Code architecture)
  const editorComponent = useMemo(() => (
    <EditorLayout
      header={
        <EditorHeader
          currentTab={currentTab}
          onTabChange={onTabChange}
          onImport={yamlOperations.handleImport}
          onExport={yamlOperations.handleExport}
          onExportAll={handleExportAll}
          onSave={handleSave}
          yamlContent={yamlContent}
          isLoading={isLoading}
          fileInputRef={yamlOperations.fileInputRef}
          saveAll={isProjectTab && !!onSaveAll}
        />
      }
      yamlContent={yamlContent}
      yamlContentComponent={
        <SimConfigYamlPanel
          yamlContent={yamlContent}
          theme={theme}
          onModuleAdd={handleAddModule}
          onConfigOpen={handleConfigOpen}
          disabled={isLoading}
        />
      }
      canvasContent={
        <div className="position-relative" style={{ height: '100%' }}>
          <ModularEventFlow
            theme={theme}
            dbConfigContent={dbConfigContent}
            projectId={projectId}
          />

          {/* Floating Toolbar for Event Flow */}
          <FloatingToolbar
            items={toolbarItems}
            position="top-center"
            theme={theme}
          />
        </div>
      }
      onResize={handleMouseDown}
      isLoading={isLoading}
    />
  ), [yamlContent, theme, isLoading, handleSave, handleAddModule, handleConfigOpen, dbConfigContent, projectId, undo, redo, canUndo, canRedo, handleMouseDown, currentTab, onTabChange, toolbarItems, yamlOperations]);

  return (
    <div className="sim-config-editor">
      {!isProjectTab && (
        <div className="mb-4 d-flex justify-content-between align-items-center">
          <div className="d-flex align-items-center">
            <h2 className="mb-0">
              {configId ? `Edit Simulation Configuration` : 'New Simulation Configuration'}
            </h2>
          </div>
        </div>
      )}

      {editorComponent}

      <input
        ref={yamlOperations.fileInputRef}
        type="file"
        accept=".yaml,.yml"
        style={{ display: 'none' }}
        onChange={yamlOperations.handleFileChange}
      />

      {/* Modals */}
      {/* Save Modal */}
      <Modal
        show={showSaveModal}
        onHide={() => setShowSaveModal(false)}
        centered
        enforceFocus={false}
      >
        <Modal.Header closeButton>
          <Modal.Title>Save Simulation Configuration</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>Save functionality will be implemented with the new store actions.</p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowSaveModal(false)}>
            Cancel
          </Button>
          <Button className="btn-custom-toolbar" onClick={() => setShowSaveModal(false)}>
            Save
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Run Modal */}
      <RunSimulationModal
        show={showRunModal}
        onHide={() => setShowRunModal(false)}
        projectId={projectId}
        yamlContent={yamlContent}
      />

      {/* Resource Configuration Modal */}
      <Modal
        show={showResourceModal}
        onHide={() => setShowResourceModal(false)}
        size="md"
        centered
        enforceFocus={false}
      >
        <Modal.Header closeButton>
          <Modal.Title>
            Resource
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <SimulationResourceEditor
            yamlContent={yamlContent}
            onResourceChange={updateYamlContent}
            theme={theme}
            dbConfigContent={dbConfigContent}
            projectId={projectId}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowResourceModal(false)}>
            Close
          </Button>
          <Button
            variant="primary"
            onClick={async () => {
              try {
                // Sync resources to YAML first, then save configuration
                syncSimulationToYaml();
                await saveConfig();
                setShowResourceModal(false);
              } catch (error) {
                showError('Failed to save resource configuration');
              }
            }}
          >
            Save
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Entity Configuration Modal */}
      <Modal
        show={showEntityModal}
        onHide={() => setShowEntityModal(false)}
        size="md"
        centered
        enforceFocus={false}
      >
        <Modal.Header closeButton>
          <Modal.Title>
            Entity
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <SimulationEntityEditor
            dbConfigContent={dbConfigContent}
            theme={theme}
            projectId={projectId}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowEntityModal(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Queue Configuration Modal */}
      <Modal
        show={showQueueModal}
        onHide={() => setShowQueueModal(false)}
        size="lg"
        centered
        enforceFocus={false}
      >
        <Modal.Header closeButton>
          <Modal.Title>
            Queue Configuration
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <SimulationQueueEditor
            projectId={projectId}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowQueueModal(false)}>
            Close
          </Button>
          <Button
            variant="primary"
            onClick={async () => {
              try {
                // Sync queues to YAML first, then save configuration
                syncSimulationToYaml();
                await saveConfig();
                setShowQueueModal(false);
              } catch (error) {
                showError('Failed to save queue configuration');
              }
            }}
          >
            Save
          </Button>
        </Modal.Footer>
      </Modal>

      {/* Simulation Configuration Modal */}
      <Modal
        show={showSimulationModal}
        onHide={() => setShowSimulationModal(false)}
        size="lg"
        centered
        enforceFocus={false}
      >
        <Modal.Header closeButton>
          <Modal.Title>
            Simulation Setup
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <SimulationSettingsEditor
            projectId={projectId}
            onClose={() => setShowSimulationModal(false)}
          />
        </Modal.Body>
      </Modal>
    </div>
  );
};

export default SimConfigEditor;