import yaml from 'yaml';
import { sortAttributes } from '../../components/database/entity-nodes/EntityNode';
import positionService from '../../services/PositionService';

/**
 * Entity YAML-related actions for the simulation config store
 * Handles YAML import, export, parsing, and validation for entity diagrams
 */
export const createEntityYamlActions = (set, get) => ({
  /**
   * Generate YAML from current canonical entities
   * @returns {string} - YAML string representation of entities
   */
  generateEntityYaml: () => {
    const { canonicalEntities } = get();

    const yamlObject = {
      entities: canonicalEntities.map(entity => ({
        name: entity.name,
        ...(entity.type && { type: entity.type }),
        rows: entity.rows || 'n/a',
        ...(entity.generator && { generator: entity.generator }),
        attributes: entity.attributes || []
      }))
    };

    const yamlString = yaml.stringify(yamlObject);

    return yamlString;
  },

  /**
   * Import YAML content from file or external source
   * @param {string} yamlContent - Raw YAML content
   * @returns {Object} - Import result with success status and message
   */
  importEntityYaml: (yamlContent) => {
    // Ensure we have a string
    if (typeof yamlContent !== 'string') {
      throw new Error('Invalid YAML content: expected string');
    }

    try {
      const parsedYAML = yaml.parse(yamlContent);
      const newEntities = parsedYAML?.entities || [];

      // Validate this is database YAML (not simulation YAML)
      if (parsedYAML?.event_simulation || parsedYAML?.steps) {
        throw new Error('Invalid YAML: This appears to be simulation configuration, not database configuration');
      }

      if (!parsedYAML?.entities) {
        throw new Error('Invalid YAML: Database configuration must contain "entities" section');
      }

      // Validate entities structure
      for (const entity of newEntities) {
        if (!entity.name) {
          throw new Error('Invalid YAML: All entities must have a "name" field');
        }
        if (!entity.attributes || !Array.isArray(entity.attributes)) {
          throw new Error(`Invalid YAML: Entity "${entity.name}" must have an "attributes" array`);
        }
      }

      // If validation passes, update canvas
      if (newEntities.length === 0) {
        set((state) => {
          state.canonicalEntities = [];
          state.entityNodes = [];
          state.entityEdges = [];
          state.dbSchema = { entities: [] };
        });
        return { success: true, message: 'Empty database configuration imported' };
      }

      // Load positions and integrate with entities
      const { projectId } = get();
      const savedPositionsMap = projectId ? positionService.getAllPositions(projectId, 'database') : new Map();
      const savedPositions = Object.fromEntries(savedPositionsMap);

      const updatedEntities = newEntities.map((entity, index) => {
        // Use saved position if available, otherwise generate grid position
        const position = savedPositions[entity.name] || {
          x: 50 + (index % 3) * 300,
          y: 100 + Math.floor(index / 3) * 200
        };

        return {
          ...entity,
          position,
          attributes: sortAttributes(entity.attributes || [])
        };
      });

      // Update store state
      set((state) => {
        state.canonicalEntities = updatedEntities;
        state.currentState = 'idle';
        state.isLoading = false;
        state.error = null;
      });

      // Update visual state
      get().updateEntityVisualState();

      // Note: Removed cleanupObsoleteEntityPositions() to prevent removing simulation step positions

      return { success: true, message: `Successfully imported ${newEntities.length} entities` };

    } catch (error) {
      set((state) => {
        state.currentState = 'idle';
        state.isLoading = false;
        state.error = error.message;
      });

      throw new Error(`YAML parsing failed: ${error.message}`);
    }
  },

  /**
   * Export current entity YAML content to file
   * @param {string} filename - Optional filename for export
   * @returns {Object} - Export result with success status and message
   */
  exportEntityYaml: (filename = 'database-config.yaml') => {
    try {
      const yamlContent = get().generateEntityYaml();

      if (!yamlContent) {
        return { success: false, message: 'No entities to export' };
      }

      const blob = new Blob([yamlContent], { type: 'text/yaml' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      return { success: true, message: 'Database configuration exported successfully' };
    } catch (error) {
      return { success: false, message: 'Export failed' };
    }
  },

  /**
   * Parse YAML content without importing (validation only)
   * @param {string} yamlContent - YAML content to validate
   * @returns {Object} - Validation result
   */
  parseEntityYaml: (yamlContent) => {
    try {
      const doc = yaml.parseDocument(yamlContent);

      if (doc.errors && doc.errors.length > 0) {
        return { valid: false, error: doc.errors[0].message };
      }

      const parsedObj = doc.toJSON();

      // Validate structure
      if (!parsedObj?.entities && parsedObj !== null) {
        return { valid: false, error: 'Invalid YAML: Missing "entities" section' };
      }

      // Validate it's not simulation YAML
      if (parsedObj?.event_simulation || parsedObj?.steps) {
        return { valid: false, error: 'Invalid YAML: This appears to be simulation configuration, not database configuration' };
      }

      return { valid: true, data: parsedObj };
    } catch (error) {
      return { valid: false, error: error.message };
    }
  },

  /**
   * Validate YAML content structure and syntax
   * @param {string} yamlContent - YAML content to validate
   * @returns {Object} - Validation result with valid flag and error message
   */
  validateEntityYaml: (yamlContent) => {
    return get().parseEntityYaml(yamlContent);
  },

  /**
   * Detect changes between entity sets
   * @param {Array} oldEntities - Previous entity list
   * @param {Array} newEntities - New entity list
   * @returns {Object} - Change detection result with added, deleted, modified arrays
   */
  detectEntityChanges: (oldEntities, newEntities) => {
    const oldNames = new Set(oldEntities.map(e => e.name));
    const newNames = new Set(newEntities.map(e => e.name));

    const added = newEntities.filter(e => !oldNames.has(e.name));
    const deleted = oldEntities.filter(e => !newNames.has(e.name));
    const modified = newEntities.filter(e => {
      const oldEntity = oldEntities.find(old => old.name === e.name);
      if (!oldEntity) return false;

      // Deep comparison of entity properties (excluding position)
      const oldClean = { ...oldEntity };
      delete oldClean.position;
      const newClean = { ...e };
      delete newClean.position;

      return JSON.stringify(oldClean) !== JSON.stringify(newClean);
    });

    return { added, deleted, modified };
  },

  /**
   * Clear all entities from the store
   * Used when switching to empty projects or resetting the diagram
   */
  clearEntities: () => {
    set((state) => {
      state.canonicalEntities = [];
      state.entityNodes = [];
      state.entityEdges = [];
      state.dbSchema = { entities: [] };
      state.selectedEntity = null;
      state.showEntityModal = false;
      state.yamlContent = '';
      state.parsedSchema = null;
    });
  },

  /**
   * Load entities from parsed YAML object
   * @param {Object} parsedObj - Parsed YAML object
   */
  loadEntitiesFromYaml: (parsedObj) => {
    if (!parsedObj || !parsedObj.entities) {
      get().clearEntities();
      return;
    }

    const { projectId } = get();
    const savedPositionsMap = projectId ? positionService.getAllPositions(projectId, 'database') : new Map();
    const savedPositions = Object.fromEntries(savedPositionsMap);

    const entities = parsedObj.entities.map((entity, index) => {
      const position = savedPositions[entity.name] || {
        x: 50 + (index % 3) * 300,
        y: 100 + Math.floor(index / 3) * 200
      };

      return {
        ...entity,
        position,
        attributes: sortAttributes(entity.attributes || [])
      };
    });

    set((state) => {
      state.canonicalEntities = entities;
    });

    // Update visual state
    get().updateEntityVisualState();
  }
});