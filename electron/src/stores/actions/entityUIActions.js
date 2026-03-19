import { pushToHistory } from '../middleware/historyActions.js';

/**
 * Entity UI-related actions for the simulation config store
 * Handles modal management, selection state, and user interaction events
 */
export const createEntityUIActions = (set, get) => ({
  /**
   * Set the currently selected entity
   * @param {Object|null} entity - Entity object or null to clear selection
   */
  setSelectedEntity: (entity) => {
    set((state) => {
      state.selectedEntity = entity;
    });
  },

  /**
   * Toggle selection mode between pan and selection
   */
  toggleSelectionMode: () => {
    set((state) => {
      state.selectionMode = !state.selectionMode;
    });
  },

  /**
   * Update entity nodes array
   * @param {Array} nodes - New nodes array
   */
  updateEntityNodes: (nodes) => {
    set((state) => {
      state.entityNodes = nodes;
    });
  },

  /**
   * Update entity edges array
   * @param {Array} edges - New edges array
   */
  updateEntityEdges: (edges) => {
    set((state) => {
      state.entityEdges = edges;
    });
  },

  /**
   * Update selected entities array
   * @param {Array} selectedNodes - Array of selected nodes
   */
  updateSelectedEntities: (selectedNodes) => {
    set((state) => {
      state.selectedEntities = selectedNodes;
      // Keep selectedEntity for backward compatibility (use first selected)
      state.selectedEntity = selectedNodes.length > 0 ? selectedNodes[0] : null;
    });
  },

  /**
   * Open entity edit modal
   * @param {Object} entity - Entity to edit
   */
  openEntityModal: (entity) => {
    set((state) => {
      state.selectedEntity = entity;
      state.showEntityModal = true;
    });
  },

  /**
   * Close entity edit modal
   */
  closeEntityModal: () => {
    set((state) => {
      state.showEntityModal = false;
      // Keep selectedEntity intact to maintain node selection consistency
      // state.selectedEntity = null;
    });
  },

  /**
   * Handle entity node click
   * @param {Event} event - Click event
   * @param {Object} node - Clicked node object
   */
  handleEntityClick: (event, node) => {
    set((state) => {
      state.selectedEntity = node;
      // Update React Flow's selection state
      state.entityNodes = state.entityNodes.map(n => ({
        ...n,
        selected: n.id === node?.id
      }));

      // Highlight connected edges when node is selected
      if (node) {
        state.entityEdges = state.entityEdges.map(edge => ({
          ...edge,
          selected: edge.source === node.id || edge.target === node.id
        }));
      } else {
        // Clear all edge selections when no node is selected
        state.entityEdges = state.entityEdges.map(edge => ({
          ...edge,
          selected: false
        }));
      }
    });
  },

  /**
   * Handle edge click (for selection)
   * @param {Event} event - Click event
   * @param {Object} edge - Clicked edge object
   */
  handleEdgeClick: (event, edge) => {
    set((state) => {
      // Clear node selection when edge is clicked
      state.selectedEntity = null;
      state.selectedEntities = [];
      state.entityNodes = state.entityNodes.map(node => ({
        ...node,
        selected: false
      }));

      // Set only the clicked edge as selected
      state.entityEdges = state.entityEdges.map(e => ({
        ...e,
        selected: e.id === edge.id
      }));

      // Update selectedEdges state
      state.selectedEdges = [edge];
    });
  },

  /**
   * Delete selected edge (remove foreign key attribute)
   */
  deleteSelectedEdge: () => {
    const state = get();
    if (state.selectedEdges.length === 0) return;

    const edge = state.selectedEdges[0];
    const sourceEntityId = edge.source;
    const targetEntityId = edge.target;

    // Push current state to history before making changes
    pushToHistory(set, get, 'database', 'UPDATE', {
      action: 'DELETE_EDGE',
      sourceEntityId,
      targetEntityId,
      edgeId: edge.id
    });

    set((state) => {
      // Find the source entity
      const sourceEntityIndex = state.canonicalEntities.findIndex(entity => entity.name === sourceEntityId);
      if (sourceEntityIndex === -1) return;

      const sourceEntity = state.canonicalEntities[sourceEntityIndex];

      // Find and remove the foreign key attribute
      const updatedAttributes = sourceEntity.attributes.filter(attr => {
        // Check if this attribute is a foreign key pointing to the target entity
        // Handle both standard FK types (fk) and simulation FK types (resource_id, entity_id)
        const isForeignKey = attr.type.startsWith('fk') ||
          attr.type === 'resource_id' ||
          attr.type === 'entity_id';

        const pointsToTarget = attr.ref && attr.ref.startsWith(`${targetEntityId}.`);

        return !(isForeignKey && pointsToTarget);
      });

      // Update the source entity
      state.canonicalEntities[sourceEntityIndex] = {
        ...sourceEntity,
        attributes: updatedAttributes
      };

      // Clear edge selection
      state.selectedEdges = [];
      state.entityEdges = state.entityEdges.map(e => ({
        ...e,
        selected: false
      }));
    });

    // Trigger visual state update
    const { updateEntityVisualState } = get();
    updateEntityVisualState();
  },

  /**
   * Handle entity node double click (open editor)
   * @param {Event} event - Double click event
   * @param {Object} node - Double-clicked node object
   */
  handleEntityDoubleClick: (event, node) => {
    get().openEntityModal(node);
  },

  /**
   * Handle entity node drag stop (update position)
   * @param {Event} event - Drag event
   * @param {Object} node - Dragged node object
   */
  handleEntityDragStop: (event, node) => {
    // Update position in both visual and canonical state
    get().updateEntityPosition(node.id, node.position);
  },

  /**
   * Handle entity nodes delete
   * @param {Array} deletedNodes - Array of deleted node objects
   */
  handleEntitiesDelete: (deletedNodes) => {
    const deletedIds = deletedNodes.map(node => node.id);
    get().deleteEntities(deletedIds);

    // Clear all selections and hide context menu
    get().clearEntitySelection();
    get().hideContextMenu();
  },

  /**
   * Handle entity update from modal
   * @param {Object} updatedEntity - Updated entity data
   */
  handleEntityUpdate: (updatedEntity) => {
    const { selectedEntity } = get();

    if (selectedEntity) {
      const updateData = {
        name: updatedEntity.name,
        type: updatedEntity.type,
        rows: updatedEntity.rows,
        attributes: updatedEntity.attributes,
        generator: updatedEntity.generator
      };

      get().updateEntity(selectedEntity.id, updateData);
    }

    // Close modal after update
    get().closeEntityModal();
  },

  /**
   * Handle entity delete from modal
   * @param {Object} entity - Entity to delete
   */
  handleEntityDelete: (entity) => {
    const { selectedEntity } = get();
    if (selectedEntity) {
      get().deleteEntity(selectedEntity.id);
    }

    // Close modal after deletion
    get().closeEntityModal();
  },

  /**
   * Clear entity selection
   */
  clearEntitySelection: () => {
    set((state) => {
      // Only update if there's actually a selection to clear
      const hasSelectedEntity = state.selectedEntity !== null;
      const hasSelectedNodes = state.entityNodes.some(node => node.selected);
      const hasSelectedEdges = state.entityEdges.some(edge => edge.selected);

      if (!hasSelectedEntity && !hasSelectedNodes && !hasSelectedEdges) {
        return; // No changes needed
      }

      state.selectedEntity = null;

      // Only update nodes if some are actually selected
      if (hasSelectedNodes) {
        state.entityNodes = state.entityNodes.map(node => ({
          ...node,
          selected: false
        }));
      }

      // Only update edges if some are actually selected  
      if (hasSelectedEdges) {
        state.entityEdges = state.entityEdges.map(edge => ({
          ...edge,
          selected: false
        }));
      }

      state.selectedEntities = [];
      state.selectedEdges = [];
    });
  },

  /**
   * Set selected edges
   * @param {Array} edges - Array of edge objects to select
   */
  setSelectedEdges: (edges) => {
    set((state) => {
      // Clear previous edge selections
      state.entityEdges = state.entityEdges.map(edge => ({
        ...edge,
        selected: false
      }));

      // Select specified edges
      edges.forEach(selectedEdge => {
        const edgeIndex = state.entityEdges.findIndex(edge => edge.id === selectedEdge.id);
        if (edgeIndex >= 0) {
          state.entityEdges[edgeIndex].selected = true;
        }
      });

      state.selectedEdges = edges;

      // Clear entity selection when selecting edges
      if (edges.length > 0) {
        state.entityNodes = state.entityNodes.map(node => ({
          ...node,
          selected: false
        }));
        state.selectedEntities = [];
        state.selectedEntity = null;
      }
    });
  },

  /**
   * Handle ReactFlow nodes change (for position updates and selection)
   * @param {Array} changes - Array of node changes
   */
  handleEntityNodesChange: (changes) => {
    let selectionChanged = false;

    changes.forEach(change => {
      if (change.type === 'position' && change.position) {
        // Update position immediately for visual feedback
        set((state) => {
          const nodeIndex = state.entityNodes.findIndex(node => node.id === change.id);
          if (nodeIndex !== -1) {
            state.entityNodes[nodeIndex].position = change.position;
          }
        });

        // Also update in canonical entities and PositionService
        get().updateEntityPosition(change.id, change.position);
      } else if (change.type === 'select') {
        selectionChanged = true;
        // Handle selection changes from React Flow
        set((state) => {
          const nodeIndex = state.entityNodes.findIndex(node => node.id === change.id);
          if (nodeIndex !== -1) {
            state.entityNodes[nodeIndex].selected = change.selected;
          }
        });
      }
    });

    // If selection changed, update selectedEntities and edge highlighting
    if (selectionChanged) {
      set((state) => {
        // Update selectedEntities array with all currently selected nodes
        const selectedNodes = state.entityNodes.filter(node => node.selected);
        state.selectedEntities = selectedNodes;

        // Keep selectedEntity for backward compatibility (use first selected)
        state.selectedEntity = selectedNodes.length > 0 ? selectedNodes[0] : null;

        // Update edge highlighting based on ALL selected nodes
        state.entityEdges = state.entityEdges.map(edge => ({
          ...edge,
          selected: selectedNodes.some(node =>
            edge.source === node.id || edge.target === node.id
          )
        }));
      });
    }
  },

  /**
   * Handle ReactFlow edges change
   * @param {Array} changes - Array of edge changes
   */
  handleEntityEdgesChange: (changes) => {
    changes.forEach(change => {
      if (change.type === 'select') {
        // Handle edge selection changes from React Flow
        set((state) => {
          const edgeIndex = state.entityEdges.findIndex(edge => edge.id === change.id);
          if (edgeIndex !== -1) {
            state.entityEdges[edgeIndex].selected = change.selected;

            // If edge is being selected, clear node selection
            if (change.selected) {
              state.selectedEntity = null;
              state.entityNodes = state.entityNodes.map(node => ({
                ...node,
                selected: false
              }));
              // Also clear other edge selections (only one edge selected at a time)
              state.entityEdges = state.entityEdges.map(edge => ({
                ...edge,
                selected: edge.id === change.id
              }));
            }
          }
        });
      }
      // Handle other edge change types if needed in the future
    });
  },

  /**
   * Handle entity connection (ReactFlow onConnect)
   * @param {Object} connection - Connection object from ReactFlow
   */
  handleEntityConnect: (connection) => {
    get().connectEntities(connection);
  },

  /**
   * Handle entity edges delete
   * @param {Array} deletedEdges - Array of deleted edge objects
   */
  handleEntityEdgesDelete: (deletedEdges) => {
    get().deleteEntityConnections(deletedEdges);
  },

  /**
   * Reset all entity UI state
   */
  resetEntityUI: () => {
    set((state) => {
      state.selectedEntity = null;
      state.showEntityModal = false;
    });
  },

  /**
   * Set entity viewport state (for ReactFlow viewport persistence)
   * @param {Object} viewport - Viewport state {x, y, zoom}
   */
  setEntityViewport: (viewport) => {
    set((state) => {
      state.entityViewportState = viewport;
    });
  },

  /**
   * Toggle entity modal visibility
   */
  toggleEntityModal: () => {
    const { showEntityModal } = get();
    if (showEntityModal) {
      get().closeEntityModal();
    } else if (get().selectedEntity) {
      get().openEntityModal(get().selectedEntity);
    }
  },

  /**
   * Copy selected entities to clipboard
   */
  copyEntities: () => {
    const { selectedEntities, canonicalEntities } = get();
    if (selectedEntities.length === 0) return;

    // Get full entity data from canonical entities
    const entitiesToCopy = selectedEntities.map(node => {
      const canonicalEntity = canonicalEntities.find(e => e.name === node.id);
      return canonicalEntity || {
        name: node.id,
        type: node.data?.tableType,
        rows: node.data?.rows,
        attributes: node.data?.attributes || []
      };
    });

    set((state) => {
      state.clipboard = entitiesToCopy;
    });
  },

  /**
   * Paste entities from clipboard at specified position
   * @param {Object} position - Position to paste entities {x, y}
   */
  pasteEntities: (position = { x: 100, y: 100 }) => {
    const { clipboard, pasteCounter, canonicalEntities } = get();
    if (clipboard.length === 0) return;

    // Generate unique names for pasted entities
    const pastedEntities = clipboard.map((entity, index) => {
      const baseName = entity.name;
      let newName = `${baseName}_${pasteCounter + index}`;

      // Ensure the name is unique
      let counter = pasteCounter + index;
      while (canonicalEntities.some(e => e.name === newName)) {
        counter++;
        newName = `${baseName}_${counter}`;
      }

      return {
        ...entity,
        name: newName,
        // Offset position for each pasted entity
        position: {
          x: position.x + (index * 50),
          y: position.y + (index * 30)
        }
      };
    });

    // Add each pasted entity
    pastedEntities.forEach(entity => {
      get().addEntity(entity, null, entity.position);
    });

    // Update paste counter
    set((state) => {
      state.pasteCounter = state.pasteCounter + clipboard.length;
    });
  },

  /**
   * Show context menu
   * @param {number} x - X position
   * @param {number} y - Y position
   */
  showContextMenu: (x, y) => {
    set((state) => {
      state.contextMenu = { visible: true, x, y };
    });
  },

  /**
   * Hide context menu
   */
  hideContextMenu: () => {
    set((state) => {
      state.contextMenu = { visible: false, x: 0, y: 0 };
    });
  },

  /**
   * Handle keyboard shortcuts for copy/paste
   * @param {KeyboardEvent} event - Keyboard event
   */
  handleEntityKeyboard: (event) => {
    // Check if user is typing in an input field
    const activeElement = document.activeElement;
    const isTyping = activeElement && (
      activeElement.tagName === 'INPUT' ||
      activeElement.tagName === 'TEXTAREA' ||
      activeElement.contentEditable === 'true'
    );

    if (isTyping) return;

    // Escape key - clear selection and close modals
    if (event.key === 'Escape') {
      get().clearEntitySelection();
      get().closeEntityModal();
      get().hideContextMenu();
      event.preventDefault();
    }

    // Copy: Ctrl+C / Cmd+C
    if ((event.ctrlKey || event.metaKey) && event.key === 'c') {
      get().copyEntities();
      event.preventDefault();
    }

    // Paste: Ctrl+V / Cmd+V
    if ((event.ctrlKey || event.metaKey) && event.key === 'v') {
      // Use a default position if no specific cursor position available
      // In ERDiagram, this will be overridden by the pasteEntities call with mousePosition
      get().pasteEntities({ x: 200, y: 200 });
      event.preventDefault();
    }
  }
});