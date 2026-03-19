import { sortAttributes } from '../../components/database/entity-nodes/EntityNode';
import {
  handleTableConnection,
  handleEdgeDeletion,
  validateConnection,
  handleTableDeletion
} from '../../components/database/entity-nodes/ERDiagramConnectionHandler';
import positionService from '../../services/PositionService';
import { pushToHistory } from '../middleware/historyActions.js';

/**
 * Entity-related actions for the simulation config store
 * Handles entity CRUD operations, position management, and visual state
 */
export const createEntityActions = (set, get) => ({
  /**
   * Add a new entity to the canvas
   * @param {Object} entityData - Entity configuration data
   * @param {Object} containerRef - Optional container ref for position calculation
   * @param {Object} viewportCenter - Optional viewport center position {x, y}
   * @returns {Object} - Created entity with position
   */
  addEntity: (entityData, containerRef = null, viewportCenter = null) => {
    // Push current state to history before making changes
    pushToHistory(set, get, 'database', 'ADD', { entityName: entityData.name });

    const { canonicalEntities, projectId } = get();

    // Calculate position for new entity
    let newPosition;
    if (viewportCenter) {
      // Use viewport center position with slight offset to avoid stacking
      const offsetX = (canonicalEntities.length % 3 - 1) * 50;
      const offsetY = Math.floor(canonicalEntities.length / 3) * 50;

      newPosition = {
        x: Math.max(50, viewportCenter.x - 100 + offsetX),
        y: Math.max(50, viewportCenter.y - 50 + offsetY)
      };
    } else if (containerRef?.current) {
      // Fallback to container center positioning
      const containerRect = containerRef.current.getBoundingClientRect();
      const centerX = containerRect.width / 2;
      const centerY = containerRect.height / 2;

      const offsetX = (canonicalEntities.length % 3 - 1) * 50;
      const offsetY = Math.floor(canonicalEntities.length / 3) * 50;

      newPosition = {
        x: Math.max(50, centerX - 100 + offsetX),
        y: Math.max(50, centerY - 100 + offsetY)
      };
    } else {
      // Fallback to grid positioning
      newPosition = {
        x: 50 + (canonicalEntities.length % 3) * 300,
        y: 100 + Math.floor(canonicalEntities.length / 3) * 200
      };
    }

    // Create new entity with position
    const newEntity = {
      ...entityData,
      position: newPosition,
      attributes: sortAttributes(entityData.attributes || [])
    };

    // Update canonical entities
    set((state) => {
      state.canonicalEntities.push(newEntity);
    });

    // Save position using PositionService
    if (projectId) {
      positionService.setPosition(projectId, entityData.name, newPosition, 'database');
    }

    // Update visual state
    get().updateEntityVisualState();

    return newEntity;
  },

  /**
   * Update an existing entity
   * @param {string} entityId - Entity identifier
   * @param {Object} newData - Updated entity data
   */
  updateEntity: (entityId, newData) => {
    // Push current state to history before making changes
    pushToHistory(set, get, 'database', 'UPDATE', { entityId, newData });

    const { projectId, canonicalEntities: currentEntities } = get();

    // Check if name is changing for position mapping update
    const isNameChanging = newData.name && newData.name !== entityId;

    set((state) => {
      const entityIndex = state.canonicalEntities.findIndex(entity => entity.name === entityId);

      if (entityIndex !== -1) {
        const currentEntity = state.canonicalEntities[entityIndex];

        const updatedEntity = {
          ...currentEntity,
          ...newData,
          position: currentEntity.position, // Preserve position
          attributes: sortAttributes(newData.attributes || currentEntity.attributes || [])
        };

        state.canonicalEntities[entityIndex] = updatedEntity;
      }
    });

    // Update position mapping if name changed
    if (isNameChanging && projectId) {
      const { canonicalEntities } = get();
      const entity = canonicalEntities.find(e => e.name === newData.name);
      if (entity && entity.position) {
        positionService.removePosition(projectId, entityId, 'database');
        positionService.setPosition(projectId, newData.name, entity.position, 'database');
      }
    }

    // Update visual state
    get().updateEntityVisualState();
  },

  /**
   * Delete an entity and clean up foreign key references
   * @param {string} entityId - Entity identifier
   */
  deleteEntity: (entityId) => {
    // Push current state to history before making changes
    pushToHistory(set, get, 'database', 'DELETE', { entityName: entityId });

    const { projectId, dbSchema } = get();

    if (dbSchema) {
      // Use enhanced deletion with foreign key cleanup
      handleTableDeletion(
        [entityId],
        dbSchema,
        (newSchema) => {
          // Update dbSchema
          set((state) => {
            state.dbSchema = newSchema;
          });

          // Update canonical entities to reflect deletion and FK cleanup
          set((state) => {
            state.canonicalEntities = state.canonicalEntities
              .filter(entity => entity.name !== entityId)
              .map(entity => {
                const updatedEntity = newSchema.entities.find(e => e.name === entity.name);
                if (updatedEntity) {
                  return {
                    ...entity,
                    attributes: updatedEntity.attributes || []
                  };
                }
                return entity;
              });
          });

          // Notify parent component through store action
          get().updateYamlAndNotify();
        }
      );
    } else {
      // Simple deletion fallback
      set((state) => {
        state.canonicalEntities = state.canonicalEntities.filter(entity => entity.name !== entityId);
      });
    }

    // Remove position
    if (projectId) {
      positionService.removePosition(projectId, entityId, 'database');
    }

    // Update visual state
    get().updateEntityVisualState();
  },

  /**
   * Update entity position
   * @param {string} entityId - Entity identifier
   * @param {Object} newPosition - New position {x, y}
   */
  updateEntityPosition: (entityId, newPosition) => {
    const { projectId } = get();

    // Update position in canonical entities
    set((state) => {
      const entityIndex = state.canonicalEntities.findIndex(entity => entity.name === entityId);
      if (entityIndex !== -1) {
        state.canonicalEntities[entityIndex].position = newPosition;
      }
    });

    // Save position using PositionService
    if (projectId) {
      positionService.setPosition(projectId, entityId, newPosition, 'database');
    }

    // Update visual nodes directly for immediate feedback
    set((state) => {
      const nodeIndex = state.entityNodes.findIndex(node => node.id === entityId);
      if (nodeIndex !== -1) {
        state.entityNodes[nodeIndex].position = newPosition;
      }
    });
  },

  /**
   * Update entity visual state (nodes and edges)
   * Transforms canonical entities to visual representation
   */
  updateEntityVisualState: () => {
    const { canonicalEntities, onEntityDiagramChange, projectId } = get();

    if (canonicalEntities.length === 0) {
      set((state) => {
        state.entityNodes = [];
        state.entityEdges = [];
        state.dbSchema = { entities: [] };
      });

      // Notify parent of empty state consistently with non-empty case
      get().updateYamlAndNotify();
      return;
    }

    // Load positions from PositionService
    const savedPositionsMap = projectId ? positionService.getAllPositions(projectId, 'database') : new Map();
    const savedPositions = Object.fromEntries(savedPositionsMap);

    // Generate visual nodes with position integration
    const visualNodes = canonicalEntities.map(entity => {
      // Use position from entity, fallback to saved positions, then default
      const position = entity.position || savedPositions[entity.name] || { x: 50, y: 50 };

      return {
        id: entity.name,
        type: 'entity',
        position: position,
        data: {
          label: entity.name,
          tableType: entity.type || '',
          rows: entity.rows || 'n/a',
          attributes: sortAttributes(entity.attributes || [])
        },
        width: 200,
        height: 100 + (entity.attributes?.length || 0) * 25,
      };
    });

    // Generate visual edges from foreign key relationships
    const visualEdges = [];
    canonicalEntities.forEach(entity => {
      if (entity.attributes) {
        entity.attributes.forEach(attr => {
          if ((attr.type === 'fk' || attr.type === 'entity_id' || attr.type === 'resource_id') && attr.ref) {
            const [targetEntity] = attr.ref.split('.');
            // Only create edge if target entity exists in canonical entities
            if (canonicalEntities.find(e => e.name === targetEntity)) {
              // Get edge metadata (handles) from PositionService
              const edgeKey = `${entity.name}-${targetEntity}`;
              const edgeMetadata = projectId ? positionService.getEdgeMetadata(projectId, edgeKey, 'database') : null;

              visualEdges.push({
                id: edgeKey,
                source: entity.name,
                sourceHandle: edgeMetadata?.sourceHandle || 'source-right',
                target: targetEntity,
                targetHandle: edgeMetadata?.targetHandle || 'source-left',
                animated: false,
                type: 'erEdge',
                style: { stroke: '#b1b7c1' },
                markerStart: 'crows-foot-many',
                markerEnd: 'crows-foot-one',
                data: {
                  markerStartType: 'crows-foot-many',
                  markerEndType: 'crows-foot-one'
                },
              });
            }
          }
        });
      }
    });

    // Update store state
    set((state) => {
      state.entityNodes = visualNodes;
      state.entityEdges = visualEdges;
      state.dbSchema = {
        entities: canonicalEntities.map(entity => ({
          name: entity.name,
          type: entity.type,
          rows: entity.rows,
          ...(entity.generator && { generator: entity.generator }),
          attributes: entity.attributes || []
        }))
      };
    });

    // Notify parent of changes through store action
    get().updateYamlAndNotify();
  },

  /**
   * Connect two entities with automatic foreign key generation
   * @param {Object} connection - ReactFlow connection object
   */
  connectEntities: (connection) => {
    const { dbSchema, onEntityDiagramChange } = get();

    // Validate connection
    if (!validateConnection(connection, dbSchema)) {
      return;
    }

    // Use enhanced connection handler
    const updatedSchema = handleTableConnection(
      connection,
      dbSchema,
      (newSchema) => {
        // Update dbSchema
        set((state) => {
          state.dbSchema = newSchema;
        });

        // Notify parent component through store action
        get().updateYamlAndNotify();
      }
    );

    if (updatedSchema) {
      // Save edge metadata (handles) to PositionService
      const { projectId } = get();
      if (projectId) {
        const edgeKey = `${connection.source}-${connection.target}`;
        positionService.setEdgeMetadata(projectId, edgeKey, {
          sourceHandle: connection.sourceHandle,
          targetHandle: connection.targetHandle
        }, 'database');
      }

      // Update canonical entities to reflect the new foreign key
      set((state) => {
        state.canonicalEntities = state.canonicalEntities.map(entity => {
          if (entity.name === connection.source) {
            const updatedEntity = updatedSchema.entities.find(e => e.name === connection.source);
            if (updatedEntity) {
              return {
                ...entity,
                attributes: updatedEntity.attributes || []
              };
            }
          }
          return entity;
        });
      });

      // Add visual edge
      const newEdge = {
        id: `${connection.source}-${connection.target}`,
        ...connection,
        animated: false,
        type: 'erEdge',
        style: { stroke: '#b1b7c1' },
        markerStart: 'crows-foot-many',
        markerEnd: 'crows-foot-one',
        data: {
          markerStartType: 'crows-foot-many',
          markerEndType: 'crows-foot-one'
        },
      };

      set((state) => {
        const existingEdgeIndex = state.entityEdges.findIndex(edge => edge.id === newEdge.id);
        if (existingEdgeIndex === -1) {
          state.entityEdges.push(newEdge);
        }
      });

      // Update visual state to reflect changes
      get().updateEntityVisualState();
    }
  },

  /**
   * Delete entity connections (edges) with automatic foreign key removal
   * @param {Array} deletedEdges - Array of deleted edge objects
   */
  deleteEntityConnections: (deletedEdges) => {
    const { dbSchema, onEntityDiagramChange } = get();

    if (dbSchema && deletedEdges.length > 0) {
      handleEdgeDeletion(
        deletedEdges,
        dbSchema,
        (newSchema) => {
          // Update dbSchema
          set((state) => {
            state.dbSchema = newSchema;
          });

          // Update canonical entities to reflect foreign key removal
          set((state) => {
            state.canonicalEntities = state.canonicalEntities.map(entity => {
              const wasSourceOfDeletedEdge = deletedEdges.some(edge => edge.source === entity.name);
              if (wasSourceOfDeletedEdge) {
                const updatedEntity = newSchema.entities.find(e => e.name === entity.name);
                if (updatedEntity) {
                  return {
                    ...entity,
                    attributes: updatedEntity.attributes || []
                  };
                }
              }
              return entity;
            });
          });

          // Remove deleted edges from visual state
          set((state) => {
            const deletedEdgeIds = deletedEdges.map(edge => edge.id);
            state.entityEdges = state.entityEdges.filter(edge => !deletedEdgeIds.includes(edge.id));
          });

          // Notify parent component through store action
          get().updateYamlAndNotify();
        }
      );
    }
  },

  /**
   * Delete multiple entities by their IDs
   * @param {Array} entityIds - Array of entity IDs to delete
   */
  deleteEntities: (entityIds) => {
    // Push current state to history before bulk deletion
    pushToHistory(set, get, 'database', 'DELETE', { entityNames: entityIds });

    // Clean up positions for deleted entities
    const { projectId } = get();
    if (projectId) {
      entityIds.forEach(entityId => {
        positionService.removePosition(projectId, entityId, 'database');
      });
    }

    // Delete entities without individual history tracking
    entityIds.forEach(entityId => {
      const { projectId, dbSchema } = get();

      if (dbSchema) {
        // Use enhanced deletion with foreign key cleanup
        handleTableDeletion(
          [entityId],
          dbSchema,
          (newSchema) => {
            // Update dbSchema
            set((state) => {
              state.dbSchema = newSchema;
            });

            // Update canonical entities to reflect deletion and FK cleanup
            set((state) => {
              state.canonicalEntities = state.canonicalEntities
                .filter(entity => entity.name !== entityId)
                .map(entity => {
                  const updatedEntity = newSchema.entities.find(e => e.name === entity.name);
                  if (updatedEntity) {
                    return {
                      ...entity,
                      attributes: updatedEntity.attributes || []
                    };
                  }
                  return entity;
                });
            });

            // Notify parent component through store action
            get().updateYamlAndNotify();
          }
        );
      } else {
        // Simple deletion fallback
        set((state) => {
          state.canonicalEntities = state.canonicalEntities.filter(entity => entity.name !== entityId);
        });
      }

      // Remove position
      if (projectId) {
        positionService.removePosition(projectId, entityId, 'database');
      }
    });

    // Update visual state after all deletions
    get().updateEntityVisualState();

    // Clear selected entities if any deleted entities were selected
    set((state) => {
      state.selectedEntities = state.selectedEntities.filter(
        entity => !entityIds.includes(entity.id || entity.name)
      );
      if (state.selectedEntity && entityIds.includes(state.selectedEntity.id || state.selectedEntity.name)) {
        state.selectedEntity = null;
      }
    });
  },

  /**
   * Set the parent callback for diagram changes
   * @param {Function} callback - Callback function for diagram changes
   */
  setEntityDiagramChangeCallback: (callback) => {
    set((state) => {
      state.onEntityDiagramChange = callback;
    });
  }
});