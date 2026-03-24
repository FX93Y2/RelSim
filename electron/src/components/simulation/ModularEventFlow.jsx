import React, { useEffect, useLayoutEffect, useRef, forwardRef, useImperativeHandle, useMemo } from 'react';
import ReactFlow, {
  Controls,
  Background,
  useReactFlow,
  ReactFlowProvider,
} from 'reactflow';
import 'reactflow/dist/style.css';

// Store imports
import {
  useSimulationConfigStore,
  useNodes,
  useEdges,
  useCanonicalSteps,
  useCurrentState,
  useSelectedNodes,
  useSelectedEdges,
  useSimulationSelectionMode,
  useCanvasActions,
  useUIActions,
  useSimulationClipboard,
  useSimulationContextMenu,
  useSimulationData,
  useShowEditModal,
  useSelectedNode
} from '../../stores/simulationConfigStore';

// Shared hooks (keep these)
import useResourceDefinitions from '../../hooks/shared/useResourceDefinitions';
import useEntityTables from '../../hooks/shared/useEntityTables';
import useRelatedEntityTables from '../../hooks/shared/useRelatedEntityTables';
import useBridgeTables from '../../hooks/shared/useBridgeTables';
import yaml from 'yaml';
import useReactFlowHandlers from '../../hooks/shared/useReactFlowHandlers';
import useTextSelectionPrevention from '../../hooks/shared/useTextSelectionPrevention';
import useContextMenuLogic from '../../hooks/shared/useContextMenu';
import useViewportPersistence from '../../hooks/shared/useViewportPersistence';

// Components
import { nodeTypes } from './flow-nodes/FlowNodeComponents';
import NodeEditModal from './flow-nodes/NodeEditModal';
import CanvasContextMenu from '../shared/CanvasContextMenu';
import { pushToHistory } from '../../stores/middleware/historyActions.js';

/**
 * Inner ModularEventFlow component that has access to ReactFlow context
 */
const ModularEventFlowInner = forwardRef(({ theme, dbConfigContent, projectId }, ref) => {
  const [initialized, setInitialized] = React.useState(false);
  const [isDragOver, setIsDragOver] = React.useState(false);
  const containerRef = useRef(null);
  const reactFlowInstance = useReactFlow();

  // Store state subscriptions (selective to prevent unnecessary re-renders)
  const nodes = useNodes(projectId);
  const edges = useEdges(projectId);
  const canonicalSteps = useCanonicalSteps(projectId);
  const currentState = useCurrentState(projectId);
  const selectedNodes = useSelectedNodes(projectId);
  const selectedEdges = useSelectedEdges(projectId);
  const selectionMode = useSimulationSelectionMode(projectId);
  const clipboard = useSimulationClipboard(projectId);
  const contextMenu = useSimulationContextMenu(projectId);
  const showEditModal = useShowEditModal(projectId);
  const selectedNode = useSelectedNode(projectId);

  // Store actions
  const {
    updateNodePosition,
    updateNodes,
    updateEdges,
    deleteNodes,
    updateStep,
    connectNodes,
    updateVisualState,
    addNode,
    groupNodes,
    ungroupNodes
  } = useCanvasActions(projectId);

  const {
    handleNodeDoubleClick,
    updateSelectedNodes,
    updateSelectedEdges,
    setSelectedEdges,
    clearSelection,
    copyNodes,
    pasteNodes,
    showContextMenu,
    hideContextMenu
  } = useUIActions(projectId);

  // Use the custom hook to get resource definitions from database config
  const resourceDefinitions = useResourceDefinitions(dbConfigContent);

  // Queue definitions are stored with the project simulation data
  const simulationData = useSimulationData(projectId);
  const queueDefinitions = simulationData?.queues || [];

  // Use the custom hooks to get entity and event tables from database config
  const entityTables = useEntityTables(dbConfigContent);
  const relatedEntityTables = useRelatedEntityTables(dbConfigContent);
  const bridgeTables = useBridgeTables(dbConfigContent);

  const entityAttributesMap = React.useMemo(() => {
    if (!dbConfigContent) return {};
    try {
      const parsed = yaml.parse(dbConfigContent);
      const map = {};
      (parsed?.entities || []).forEach(entity => {
        if (entity?.name && Array.isArray(entity.attributes)) {
          map[entity.name] = entity.attributes
            .map(a => a.name)
            .filter(Boolean)
            .sort();
        }
      });
      return map;
    } catch (e) {
      console.error('[ModularEventFlow] Failed to parse db config for attributes:', e);
      return {};
    }
  }, [dbConfigContent]);

  // Get project-specific store state when needed (non-reactive)
  const getStoreState = () => useSimulationConfigStore(projectId).getState();

  // Use shared viewport persistence hook
  const {
    viewport,
    handleViewportMove,
    handleViewportMoveStart,
    handleViewportMoveEnd
  } = useViewportPersistence(projectId, 'simulation', reactFlowInstance, initialized);

  // Use layout effect to ensure container is measured before rendering
  useLayoutEffect(() => {
    if (containerRef.current) {
      setInitialized(true);
    }
  }, []);



  // Position management is now handled directly by the store

  // Sync canonical steps to visual representation when they change
  useEffect(() => {
    if (currentState !== 'importing') { // Don't sync during imports
      updateVisualState();
    }
  }, [canonicalSteps, currentState]);

  // Create getEdges function that gets current edges from store
  const getEdges = React.useCallback(() => {
    return useSimulationConfigStore(projectId).getState().edges;
  }, [projectId]);

  // Use shared ReactFlow handlers for consistent behavior
  const { onNodesChange, onEdgesChange } = useReactFlowHandlers({
    nodes,
    getEdges,
    updateNodes,
    updateEdges,
    updateSelected: updateSelectedNodes,
    onPositionChange: updateNodePosition
  });


  // Enhanced text selection prevention with mouse events
  useTextSelectionPrevention(containerRef, true);

  // Use shared context menu hook
  const contextMenuHook = useContextMenuLogic({
    selectionMode,
    selectedItems: selectedNodes,
    clipboard,
    onCopy: copyNodes,
    onPaste: pasteNodes,
    onDelete: (nodes) => {
      const nodeIds = nodes.map(node => node.id);
      deleteNodes(nodeIds);
    },
    onShowContextMenu: showContextMenu,
    onHideContextMenu: hideContextMenu,
    onHideContextMenu: hideContextMenu,
    onGroup: groupNodes,
    onUngroup: ungroupNodes,
    reactFlowInstance
  });

  const onConnect = React.useCallback((connection) => {
    connectNodes(connection);
  }, [connectNodes]);


  const onNodeDoubleClick = React.useCallback((_, node) => {
    handleNodeDoubleClick(_, node);
  }, [handleNodeDoubleClick]);

  const onNodeDragStop = React.useCallback((_, node) => {
    // Position updates are already handled by onNodesChange, but let's keep this as backup
    updateNodePosition(node.id, node.position);
  }, [updateNodePosition]);

  const onNodesDelete = React.useCallback((deletedNodes) => {
    const deletedIds = deletedNodes.map(n => n.id);
    deleteNodes(deletedIds);
  }, [deleteNodes]);

  const onEdgesDelete = React.useCallback(() => {
    // Edge deletion handled by node deletion cleanup
  }, []);

  // Edge click handler to select edges
  const onEdgeClick = React.useCallback((event, edge) => {
    event.stopPropagation();
    setSelectedEdges([edge]);
  }, [setSelectedEdges]);

  // Edge context menu handler  
  const onEdgeContextMenu = React.useCallback((event, edge) => {
    event.preventDefault();
    event.stopPropagation();
    setSelectedEdges([edge]);

    const clientX = event.nativeEvent?.clientX ?? event.clientX;
    const clientY = event.nativeEvent?.clientY ?? event.clientY;
    showContextMenu(clientX, clientY);
  }, [setSelectedEdges, showContextMenu]);

  // Edge deletion handler
  const onDeleteEdge = React.useCallback(() => {
    if (selectedEdges.length === 0) return;

    const edge = selectedEdges[0];
    const sourceNodeId = edge.source;
    const targetNodeId = edge.target;
    const handleId = edge.sourceHandle;

    // Find the source step in canonical steps
    const sourceStep = canonicalSteps.find(step => step.step_id === sourceNodeId);
    if (!sourceStep) return;

    // Push current state to history before making changes
    const store = useSimulationConfigStore(projectId);
    pushToHistory(store.setState, store.getState, 'simulation', 'UPDATE', {
      action: 'DELETE_EDGE',
      sourceStepId: sourceNodeId,
      targetStepId: targetNodeId,
      handleId
    });

    if (sourceStep.step_type === 'decide' && handleId) {
      // For decision steps, clear the specific outcome next_step_id
      const outcomeIndex = parseInt(handleId.replace('outcome-', ''));
      if (sourceStep.decide_config?.outcomes?.[outcomeIndex]) {
        const updatedStep = {
          ...sourceStep,
          decide_config: {
            ...sourceStep.decide_config,
            outcomes: sourceStep.decide_config.outcomes.map((outcome, idx) =>
              idx === outcomeIndex ? { ...outcome, next_step_id: '' } : outcome
            )
          }
        };
        updateStep(sourceStep.step_id, updatedStep);
      }
    } else {
      // For regular steps, remove from next_steps array
      if (sourceStep.next_steps && Array.isArray(sourceStep.next_steps)) {
        const updatedStep = {
          ...sourceStep,
          next_steps: sourceStep.next_steps.filter(stepId => stepId !== targetNodeId)
        };
        updateStep(sourceStep.step_id, updatedStep);
      } else if (sourceStep.next_steps === targetNodeId) {
        // Handle case where next_steps is a single step_id string
        const updatedStep = {
          ...sourceStep,
          next_steps: []
        };
        updateStep(sourceStep.step_id, updatedStep);
      }
    }

    // Clear edge selection and update visual state
    clearSelection();
    updateVisualState();
    hideContextMenu();
  }, [selectedEdges, canonicalSteps, updateStep, clearSelection, updateVisualState, hideContextMenu]);

  const onConnectStart = React.useCallback((event) => {
    // Prevent default text selection during edge dragging
    event.preventDefault();
    document.body.classList.add('react-flow-connecting');
  }, []);

  const onConnectEnd = React.useCallback(() => {
    // Re-enable text selection after edge dragging
    document.body.classList.remove('react-flow-connecting');
  }, []);


  const onDragOver = React.useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    setIsDragOver(true);
  }, []);

  const onDragLeave = React.useCallback((event) => {
    // Check if we're leaving the canvas entirely
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setIsDragOver(false);
    }
  }, []);

  const onDrop = React.useCallback((event) => {
    event.preventDefault();
    setIsDragOver(false);

    // Get the data from the drag event
    const dataString = event.dataTransfer.getData('application/reactflow');
    if (!dataString) {
      console.warn('⚠️ ReactFlow: No drag data found');
      return;
    }

    const dragData = JSON.parse(dataString);
    const moduleType = dragData.type;

    // Check if ReactFlow instance is available
    if (!reactFlowInstance) {
      console.error('ModularEventFlow: ReactFlow instance not available');
      return;
    }

    // Get the position where the node was dropped
    const position = reactFlowInstance.screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });

    // Center the node on cursor (subtract half of typical node size)
    position.x -= 40;
    position.y -= 40;

    // Generate a unique step ID
    const existingStepIds = canonicalSteps.map(s => s.step_id);
    const generateStepId = (stepType) => {
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
    };

    const stepId = generateStepId(moduleType);

    // Create step configuration based on type
    let newStep = {
      step_id: stepId,
      step_type: moduleType
    };

    switch (moduleType) {
      case 'event':
        newStep.event_config = {
          duration: { formula: '' },
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
          max_entities: "n/a"
        };
        break;
      case 'trigger':
        newStep.trigger_config = {
          target_table: "",
          count: 1,
          fk_column: ""
        };
        break;
      default:
        console.warn('Unknown module type:', moduleType);
        return;
    }

    // Add the node at the drop position
    addNode(newStep, position);
  }, [reactFlowInstance, canonicalSteps, addNode]);


  // Handle node updates from modal
  const handleNodeUpdate = React.useCallback((updatedNode) => {
    const { selectedNode } = getStoreState();
    if (!selectedNode) return;


    updateStep(selectedNode.id, {
      ...updatedNode.data.stepConfig,
      step_id: updatedNode.id
    });
  }, [updateStep, getStoreState]);

  // Close modal handler
  const closeModal = React.useCallback(() => {
    const state = getStoreState();
    state.setShowEditModal(false);
  }, [getStoreState]);

  // Note: Keyboard event handling now done by useContextMenuLogic hook

  // Add event listener for right-clicks when nodes are selected
  React.useEffect(() => {
    if (selectionMode && selectedNodes.length > 0) {
      const handleSelectionContextMenu = (e) => {
        // Check if the click is within the flow container
        const flowContainer = e.target.closest('.modular-event-flow');
        if (flowContainer) {
          e.preventDefault();
          e.stopPropagation();
          // Show context menu at cursor position
          showContextMenu(e.clientX, e.clientY);
        }
      };

      // Use capture phase to intercept before other handlers
      document.addEventListener('contextmenu', handleSelectionContextMenu, true);
      return () => {
        document.removeEventListener('contextmenu', handleSelectionContextMenu, true);
      };
    }
  }, [selectionMode, selectedNodes, showContextMenu]);

  // Imperative methods for parent components (if needed)
  const imperativeMethods = useMemo(() => ({
    addStep: (stepData) => {
      // Get viewport center for positioning new steps
      const viewport = reactFlowInstance.getViewport();
      const position = containerRef.current
        ? {
          x: -viewport.x + (containerRef.current.clientWidth || 800) / 2 / viewport.zoom - 100,
          y: -viewport.y + (containerRef.current.clientHeight || 600) / 2 / viewport.zoom - 50
        }
        : { x: 100, y: 100 };

      addNode(stepData, position);
    },
    updateStep,
    deleteStep: (stepId) => deleteNodes([stepId]),
    getCanonicalSteps: () => getStoreState().canonicalSteps
  }), [addNode, updateStep, deleteNodes, getStoreState, reactFlowInstance]);

  // Expose methods to parent components
  useImperativeHandle(ref, () => imperativeMethods, [imperativeMethods]);

  // If not initialized, just show the container to get dimensions
  if (!initialized) {
    return (
      <div
        ref={containerRef}
        className="modular-event-flow event-flow-container"
        style={{
          width: '100%',
          height: '100%',
          borderRadius: '4px',
          overflow: 'hidden'
        }}
      />
    );
  }

  return (
    <div ref={containerRef} className={`modular-event-flow event-flow-container ${selectionMode ? 'selection-mode' : ''} ${isDragOver ? 'drag-over' : ''}`} style={{ width: '100%', height: '100%' }}>
      {initialized && (
        <div id="modular-event-flow-wrapper" style={{ width: '100%', height: '100%' }}>
          <ReactFlow
            id="modular-event-flow-instance"
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectStart={onConnectStart}
            onConnectEnd={onConnectEnd}
            onNodeDoubleClick={onNodeDoubleClick}
            onNodeDragStop={onNodeDragStop}
            onNodeContextMenu={contextMenuHook.onNodeContextMenu}
            onEdgeClick={onEdgeClick}
            onEdgeContextMenu={onEdgeContextMenu}
            onPaneClick={(event) => {
              clearSelection();
              contextMenuHook.onPaneClick(event);
            }}
            onPaneContextMenu={contextMenuHook.onPaneContextMenu}
            onNodesDelete={onNodesDelete}
            onEdgesDelete={onEdgesDelete}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            nodeTypes={nodeTypes}
            snapToGrid={true}
            snapGrid={[20, 20]}
            fitView={false}
            onMove={handleViewportMove}
            onMoveStart={handleViewportMoveStart}
            onMoveEnd={handleViewportMoveEnd}
            attributionPosition="bottom-right"
            nodesDraggable={true}
            elementsSelectable={true}
            edgesFocusable={true}
            multiSelectionKeyCode={selectionMode ? false : ['Control', 'Meta', 'Shift']}
            selectionOnDrag={selectionMode}
            panOnDrag={!selectionMode}
            deleteKeyCode={null}
          >
            <Background
              key="modular-event-flow-background"
              variant="dots"
              gap={12}
              size={1}
            />
            <Controls position="bottom-right" />
          </ReactFlow>
        </div>
      )}

      <NodeEditModal
        show={showEditModal}
        onHide={closeModal}
        node={selectedNode}
        onNodeUpdate={handleNodeUpdate}
        onNodeDelete={onNodesDelete}
        theme={theme}
        parsedSchema={getStoreState().parsedSchema}
        resourceDefinitions={resourceDefinitions}
        queueDefinitions={queueDefinitions}
        entityTables={entityTables}
        relatedEntityTables={relatedEntityTables}
        entityAttributesMap={entityAttributesMap}
        bridgeTables={bridgeTables}
      />
      <CanvasContextMenu
        visible={contextMenu.visible}
        x={contextMenu.x}
        y={contextMenu.y}
        onCopy={contextMenuHook.handleContextCopy}
        onPaste={contextMenuHook.handleContextPaste}
        onDelete={contextMenuHook.handleContextDelete}
        onGroup={contextMenuHook.handleContextGroup}
        onUngroup={contextMenuHook.handleContextUngroup}
        onDeleteEdge={onDeleteEdge}
        hasClipboard={clipboard.length > 0}
        hasSelection={selectedNodes.length > 0}
        hasEdgeSelection={selectedEdges.length > 0}
        canGroup={selectedNodes.length > 1}
        canUngroup={selectedNodes.some(n => n.data?.stepConfig?.group_id)}
        itemType="node"
      />
    </div>
  );
});

ModularEventFlowInner.displayName = 'ModularEventFlowInner';

/**
 * Main ModularEventFlow component with ReactFlow provider
 */
const ModularEventFlow = forwardRef(({ theme, dbConfigContent, projectId }, ref) => {
  return (
    <ReactFlowProvider>
      <ModularEventFlowInner
        theme={theme}
        dbConfigContent={dbConfigContent}
        projectId={projectId}
        ref={ref}
      />
    </ReactFlowProvider>
  );
});

ModularEventFlow.displayName = 'ModularEventFlow';

export default ModularEventFlow;
