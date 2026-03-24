import React, { useState, useEffect } from 'react';
import { Modal, Button } from 'react-bootstrap';
import { FiTrash2 } from 'react-icons/fi';
import ConfirmationModal from '../../shared/ConfirmationModal';
import { useStepHelpers } from './hooks/useStepHelpers';
import EventStepEditor from './editors/EventStepEditor';
import DecideStepEditor from './editors/DecideStepEditor';
import AssignStepEditor from './editors/AssignStepEditor';
import ReleaseStepEditor from './editors/ReleaseStepEditor';
import CreateStepEditor from './editors/CreateStepEditor';
import TriggerStepEditor from './editors/TriggerStepEditor';
import { convertDistributionToFormula } from '../../shared/distribution';

// Helper function to convert old distribution format to formula
const convertOldDistributionToFormula = (distribution) => {
  if (!distribution) return '';
  return convertDistributionToFormula(distribution);
};

const NodeEditModal = ({ show, onHide, node, onNodeUpdate, onNodeDelete, theme, parsedSchema, resourceDefinitions, queueDefinitions = [], entityTables = [], relatedEntityTables = {}, entityAttributesMap = {}, bridgeTables = [] }) => {
  const [formData, setFormData] = useState({});
  const [resourceRequirements, setResourceRequirements] = useState([]);
  const [outcomes, setOutcomes] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [nameValidation, setNameValidation] = useState({ valid: true, error: null });

  // Use the step helpers hook
  const {
    getAvailableStepNames,
    validateStepId
  } = useStepHelpers(parsedSchema);

  // Reset form data whenever modal opens or the selected node changes to ensure clean state
  useEffect(() => {
    if (show && node?.data?.stepConfig) {
      initializeFormData(node.data.stepConfig);
    }
  }, [show, node?.id, parsedSchema]);

  // Validate initial name when form data is initialized
  useEffect(() => {
    if (formData.name !== undefined) {
      validateStepName(formData.name);
    }
  }, [formData.name, node, parsedSchema]);

  const currentStepId = node?.data?.stepConfig?.step_id;

  const flowEntityTable = React.useMemo(() => {
    if (!currentStepId || !parsedSchema?.event_simulation?.event_flows) {
      return null;
    }

    for (const flow of parsedSchema.event_simulation.event_flows) {
      if (!flow?.steps) continue;
      const containsStep = flow.steps.some(step => step.step_id === currentStepId);
      if (!containsStep) continue;

      const createStep = flow.steps.find(
        step => step.step_type === 'create' && step.create_config?.entity_table
      );
      if (createStep?.create_config?.entity_table) {
        return createStep.create_config.entity_table;
      }
    }

    return null;
  }, [currentStepId, parsedSchema]);

  const availableTargetTables = React.useMemo(() => {
    if (!flowEntityTable) return [];
    return relatedEntityTables?.[flowEntityTable] || [];
  }, [flowEntityTable, relatedEntityTables]);

  const initializeFormData = (stepConfig, nodeData = node) => {
    if (stepConfig.step_type === 'event') {
      initializeEventForm(stepConfig);
    } else if (stepConfig.step_type === 'decide') {
      initializeDecideForm(stepConfig);
    } else if (stepConfig.step_type === 'assign') {
      initializeAssignForm(stepConfig);
    } else if (stepConfig.step_type === 'release') {
      initializeReleaseForm(stepConfig);
    } else if (stepConfig.step_type === 'create') {
      initializeCreateForm(stepConfig, nodeData);
    } else if (stepConfig.step_type === 'trigger') {
      initializeTriggerForm(stepConfig);
    }
  };

  const getFlowForNode = () => {
    if (!parsedSchema?.event_simulation?.event_flows || !node) return null;
    return parsedSchema.event_simulation.event_flows.find(flow =>
      flow?.steps?.some(step => step.step_id === node.id)
    ) || null;
  };

  const getEntityTableForFlow = (flow) => {
    if (!flow) return '';
    const createStep = flow.steps?.find(
      s => s.step_type === 'create' && s.create_config?.entity_table
    );
    if (createStep?.create_config?.entity_table) {
      return createStep.create_config.entity_table;
    }
    const tableSpec = parsedSchema?.event_simulation?.table_specification;
    return tableSpec?.entity_table || '';
  };

  const getAvailableAttributesForCurrentFlow = () => {
    // ... existing implementation ...
    const attrs = new Set();
    const flow = getFlowForNode();
    const entityTable = getEntityTableForFlow(flow);
    const entityAttrs = entityAttributesMap[entityTable];
    if (Array.isArray(entityAttrs)) {
      entityAttrs.forEach(name => attrs.add(name));
    } else {
      const entities = parsedSchema?.database_schema?.entities || parsedSchema?.db_config?.entities || [];
      const entity = entities.find(e => e.name === entityTable);
      if (entity?.attributes) {
        entity.attributes.forEach(attr => {
          if (attr.name) attrs.add(attr.name);
        });
      }
    }
    flow?.steps?.forEach(step => {
      if (step.step_type === 'assign' && step.assign_config?.assignments) {
        step.assign_config.assignments.forEach(assignment => {
          if (assignment.attribute_name) {
            attrs.add(assignment.attribute_name);
          }
        });
      }
    });
    return Array.from(attrs).sort();
  };

  const stepTypes = React.useMemo(() => {
    if (!parsedSchema?.event_simulation?.event_flows) return {};
    const types = {};
    parsedSchema.event_simulation.event_flows.forEach(flow => {
      flow?.steps?.forEach(step => {
        if (step.step_id && step.step_type) {
          types[step.step_id] = step.step_type;
        }
      });
    });
    return types;
  }, [parsedSchema]);

  const initializeEventForm = (stepConfig) => {
    const eventConfig = stepConfig.event_config || {};
    const duration = eventConfig.duration || {};

    // Use step_id as the display name
    const stepName = stepConfig.step_id || '';

    setFormData({
      name: stepName,
      bridge_table: eventConfig.bridge_table || '',
      duration_formula: duration.formula || (duration.distribution ? convertOldDistributionToFormula(duration.distribution) : ''),
      duration_time_unit: duration.time_unit || undefined,
      // Keep old format for backward compatibility during migration
      distribution_type: duration.distribution?.type || 'normal',
      duration_mean: duration.distribution?.mean || 1,
      duration_stddev: duration.distribution?.stddev || 0.1,
      duration_scale: duration.distribution?.scale || 1,
      duration_min: duration.distribution?.min || 0,
      duration_max: duration.distribution?.max || 10,
      duration_values: duration.distribution?.values ? duration.distribution.values.join(', ') : '1, 2, 3',
      duration_weights: duration.distribution?.weights ? duration.distribution.weights.join(', ') : '0.5, 0.3, 0.2',
      _initializedForNode: node?.id
    });

    setResourceRequirements(eventConfig.resource_requirements || []);
  };

  const initializeDecideForm = (stepConfig) => {
    const decideConfig = stepConfig.decide_config || {};

    // Use step_id as the display name
    const stepName = stepConfig.step_id || '';

    setFormData({
      name: stepName,
      decision_type: decideConfig.decision_type || '2way-chance',
      _initializedForNode: node?.id
    });

    // Convert outcomes to use step IDs as display names (step_id is the display name)
    const convertedOutcomes = (decideConfig.outcomes || []).map((outcome) => {
      const nextStepId = outcome.next_step_id;
      const condition = outcome.conditions?.[0] || {};

      const convertedOutcome = {
        next_event_name: nextStepId || ''
      };

      if (condition.if && condition.if.toLowerCase() === 'probability') {
        convertedOutcome.probability = condition.value || 0.5;
      } else {
        // Attribute-based condition
        convertedOutcome.if = condition.if || 'Attribute';
        convertedOutcome.name = condition.name || '';
        convertedOutcome.is = condition.is || '==';
        convertedOutcome.value = condition.value || '';
      }

      return convertedOutcome;
    });

    // Ensure at least 2 outcomes with appropriate defaults based on decision type
    if (convertedOutcomes.length === 0) {
      const currentDecisionType = decideConfig.decision_type || '2way-chance';
      const isCondition = currentDecisionType.includes('condition');

      if (isCondition) {
        setOutcomes([
          { next_event_name: '', if: 'Attribute', name: '', is: '==', value: '' },
          { next_event_name: '', if: 'Attribute', name: '', is: '==', value: '' }
        ]);
      } else {
        setOutcomes([
          { next_event_name: '', probability: 0.7 },
          { next_event_name: '', probability: 0.3 }
        ]);
      }
    } else {
      // For 2-way decisions, ensure we have exactly 2 outcomes
      if (decideConfig.decision_type?.startsWith('2way') && convertedOutcomes.length < 2) {
        const secondOutcome = decideConfig.decision_type.includes('condition')
          ? { next_event_name: '', if: 'Attribute', name: '', is: '==', value: '' }
          : { next_event_name: '', probability: 0.3 };
        setOutcomes([...convertedOutcomes, secondOutcome]);
      } else {
        setOutcomes(convertedOutcomes);
      }
    }
  };

  const initializeAssignForm = (stepConfig) => {
    const assignConfig = stepConfig.assign_config || {};

    // Use step_id as the display name
    const stepName = stepConfig.step_id || '';

    setFormData({
      name: stepName,
      _initializedForNode: node?.id
    });

    // Initialize assignments
    const convertedAssignments = (assignConfig.assignments || []).map((assignment) => ({
      assignment_type: assignment.assignment_type || 'attribute',
      attribute_name: assignment.attribute_name || '',
      // Preserve both fields; UI and save logic will pick correct one by type
      value: assignment.value ?? '',
      expression: assignment.expression || ''
    }));

    // Ensure at least one assignment
    if (convertedAssignments.length === 0) {
      setAssignments([{
        assignment_type: 'attribute',
        attribute_name: '',
        value: ''
      }]);
    } else {
      setAssignments(convertedAssignments);
    }
  };

  const initializeReleaseForm = (stepConfig) => {
    // Use step_id as the display name
    const stepName = stepConfig.step_id || 'Release';

    setFormData({
      name: stepName,
      _initializedForNode: node?.id
    });
  };

  const initializeCreateForm = (stepConfig, nodeData) => {
    const createConfig = stepConfig.create_config || {};
    const interarrivalTime = createConfig.interarrival_time || {};

    // Use step_id as the display name
    const stepName = stepConfig.step_id || '';

    // Get event flow label from stepConfig (legacy field is migrated during YAML parse/import)
    const savedEventFlow = stepConfig._eventFlow || '';

    setFormData({
      name: stepName,
      entity_table: createConfig.entity_table || '',
      event_flow: savedEventFlow,
      interarrival_formula: interarrivalTime.formula || (interarrivalTime.distribution ? convertOldDistributionToFormula(interarrivalTime.distribution) : ''),
      interarrival_time_unit: interarrivalTime.time_unit || undefined,
      max_entities: createConfig.max_entities || 'n/a',
      next_step: stepConfig.next_steps && stepConfig.next_steps.length > 0 ? stepConfig.next_steps[0] : '',
      next_steps: stepConfig.next_steps || [],
      is_triggered: !interarrivalTime || (!interarrivalTime.formula && !interarrivalTime.distribution),
      _initializedForNode: node?.id
    });
  };

  const initializeTriggerForm = (stepConfig) => {
    const triggerConfig = stepConfig.trigger_config || {};

    // Use step_id as the display name
    const stepName = stepConfig.step_id || '';

    setFormData({
      name: stepName,
      target_table: triggerConfig.target_table || '',
      count: triggerConfig.count !== undefined ? triggerConfig.count : 1,
      fk_column: triggerConfig.fk_column || '',
      next_step: stepConfig.next_steps && stepConfig.next_steps.length > 0 ? stepConfig.next_steps[0] : '',
      _initializedForNode: node?.id
    });
  };

  // Helper function to handle form data changes
  const handleFormDataChange = (newData) => {
    setFormData(prev => ({ ...prev, ...newData }));

    // Validate step name when it changes
    if (newData.name !== undefined) {
      validateStepName(newData.name);
    }
  };

  // Validate step name and update validation state
  const validateStepName = (stepName) => {
    if (!node) {
      setNameValidation({ valid: true, error: null });
      return;
    }

    const currentStepId = node.data.stepConfig?.step_id;
    const validation = validateStepId(stepName, currentStepId);
    setNameValidation(validation);
  };

  // Resource requirement handlers
  const handleResourceRequirementChange = (index, field, value) => {
    setResourceRequirements((prevRequirements) => {
      const updatedRequirements = [...prevRequirements];
      updatedRequirements[index] = {
        ...updatedRequirements[index],
        [field]: value
      };
      return updatedRequirements;
    });
  };

  const addResourceRequirement = () => {
    const availableResourceTables = Object.keys(resourceDefinitions);
    if (availableResourceTables.length === 0) {
      return; // Don't add if no resource tables available
    }

    const defaultResourceTable = availableResourceTables[0];
    const defaultResourceType = resourceDefinitions[defaultResourceTable]?.resourceTypes?.length > 0
      ? resourceDefinitions[defaultResourceTable].resourceTypes[0]
      : '';

    setResourceRequirements([...resourceRequirements, {
      resource_table: defaultResourceTable,
      value: defaultResourceType,
      count: 1,
      queue: ''
    }]);
  };

  const removeResourceRequirement = (index) => {
    setResourceRequirements(resourceRequirements.filter((_, i) => i !== index));
  };

  // Outcome handlers
  const handleOutcomeChange = (index, field, value) => {
    const updated = [...outcomes];
    updated[index] = { ...updated[index], [field]: value };

    // For 2-way chance decisions, auto-calculate "else" probability
    if (formData.decision_type === '2way-chance' && field === 'probability' && index === 0) {
      const primaryProb = parseFloat(value) || 0;
      if (updated.length > 1) {
        updated[1] = { ...updated[1], probability: 1 - primaryProb };
      }
    }

    setOutcomes(updated);
  };

  const addOutcome = () => {
    const isCondition = formData.decision_type?.includes('condition');
    if (isCondition) {
      setOutcomes([...outcomes, {
        next_event_name: '',
        if: 'Attribute',
        name: '',
        is: '==',
        value: ''
      }]);
    } else {
      setOutcomes([...outcomes, {
        next_event_name: '',
        probability: 0.5
      }]);
    }
  };

  const removeOutcome = (index) => {
    if (outcomes.length > 1) {
      setOutcomes(outcomes.filter((_, i) => i !== index));
    }
  };

  // Assignment handlers
  const handleAssignmentChange = (index, field, value) => {
    // Process the value to handle numeric strings properly for YAML
    let processedValue = value;
    if (field === 'value' && value) {
      // Try to convert to number if it's a valid numeric string
      if (/^\d+(\.\d+)?$/.test(value.toString())) {
        processedValue = value.includes('.') ? parseFloat(value) : parseInt(value, 10);
      }
    }

    const updated = [...assignments];
    updated[index] = { ...updated[index], [field]: processedValue };
    setAssignments(updated);
  };

  const addAssignment = () => {
    setAssignments([...assignments, {
      assignment_type: 'attribute',
      attribute_name: '',
      value: ''
    }]);
  };

  const removeAssignment = (index) => {
    if (assignments.length > 1) {
      setAssignments(assignments.filter((_, i) => i !== index));
    }
  };

  // Handle node deletion - direct delete without confirmation since undo/redo is available
  const handleDelete = () => {
    try {
      onNodeDelete([node]); // Pass as array since onNodesDelete expects array
      onHide();
    } catch (error) {
      console.error('Error deleting node:', error);
    }
  };

  // Handle save and close
  const handleSaveAndClose = () => {
    if (forceSave()) {
      onHide();
    }
  };

  // Force immediate save without debounce
  const forceSave = () => {
    if (!node) {
      return false; // Don't save if no node
    }

    // Check name validation first
    if (!nameValidation.valid) {
      console.warn('Cannot save step with invalid name:', nameValidation.error);
      return false; // Don't save if name validation fails
    }

    // Validation depends on step type
    const stepType = node.data.stepConfig.step_type;
    if ((stepType === 'event' || stepType === 'release') && !formData.name) {
      return false; // Don't save if basic validation fails for event/release
    }
    if (stepType === 'assign') {
      if (assignments.length === 0) {
        return false; // Don't save if no assignments for assign step
      }
      // Validate all assignments have required fields
      for (const assignment of assignments) {
        const isSql = assignment.assignment_type === 'sql';
        const hasValue = isSql
          ? (assignment.expression && assignment.expression.toString().trim() !== '')
          : (assignment.value !== undefined && assignment.value !== '' && assignment.value !== null);

        // Attribute name is required only for non-SQL assignments
        const requiresAttribute = !isSql;

        if ((requiresAttribute && !assignment.attribute_name) || !hasValue) {
          return false; // Don't save if any assignment is incomplete
        }
      }
    }
    if (stepType === 'create') {
      if (!formData.entity_table) {
        return false; // Don't save if essential create fields are missing
      }
      // For Create modules, next_step is optional when there are no other steps yet
      // This allows Create to be the first step in a flow
    }

    try {
      const updatedStepConfig = buildStepConfig();
      const updatedNode = {
        ...node,
        id: updatedStepConfig.step_id,
        data: {
          ...node.data,
          stepConfig: updatedStepConfig,
          label: generateLabel(node.data.stepConfig.step_type, formData, updatedStepConfig.step_id),
        }
      };


      onNodeUpdate(updatedNode);
      return true;
    } catch (error) {
      console.error('Error saving node:', error);
      return false;
    }
  };

  const buildStepConfig = () => {
    const stepType = node.data.stepConfig.step_type;
    const stepId = generateStepId(stepType, formData);
    const updatedStepConfig = {
      ...node.data.stepConfig,
      step_id: stepId
    };

    if (stepType === 'event') {
      updatedStepConfig.event_config = buildEventConfig();
    } else if (stepType === 'decide') {
      updatedStepConfig.decide_config = buildDecideConfig(stepId);
    } else if (stepType === 'assign') {
      updatedStepConfig.assign_config = buildAssignConfig(stepId);
      // Preserve existing next_steps for assign nodes (connections handled via canvas)
    } else if (stepType === 'release') {
      // Release steps should not include event_config in YAML
      if (updatedStepConfig.event_config) {
        delete updatedStepConfig.event_config;
      }
    } else if (stepType === 'create') {
      updatedStepConfig.create_config = buildCreateConfig();
      // Use next_steps if available, otherwise fall back to next_step (singlet)
      updatedStepConfig.next_steps = formData.next_steps && formData.next_steps.length > 0
        ? [...new Set(formData.next_steps)] // Deduplicate
        : (formData.next_step ? [formData.next_step] : []);
      // Store event_flow in stepConfig for YAML generation (not in create_config)
      updatedStepConfig._eventFlow = formData.event_flow || '';
    } else if (stepType === 'trigger') {
      updatedStepConfig.trigger_config = buildTriggerStepConfig();
      updatedStepConfig.next_steps = formData.next_step ? [formData.next_step] : [];
    }

    return updatedStepConfig;
  };

  const buildEventConfig = () => {
    const duration = { formula: formData.duration_formula || '' };
    if (formData.duration_time_unit) {
      duration.time_unit = formData.duration_time_unit;
    }

    const sanitizedRequirements = resourceRequirements.map((req) => {
      const requirement = { ...req };

      if (requirement.queue) {
        const trimmedQueue = requirement.queue.trim();
        if (trimmedQueue) {
          requirement.queue = trimmedQueue;
        } else {
          delete requirement.queue;
        }
      } else {
        delete requirement.queue;
      }

      return requirement;
    });

    const eventConfig = {
      duration,
      resource_requirements: sanitizedRequirements
    };

    // Add bridge_table if set
    if (formData.bridge_table) {
      eventConfig.bridge_table = formData.bridge_table;
    }

    return eventConfig;
  };

  const buildDecideConfig = (stepId) => {
    // Convert outcomes back to step IDs with proper conditions
    const convertedOutcomes = outcomes.map((outcome, index) => {
      const baseOutcome = {
        outcome_id: `outcome_${index + 1}`,
        next_step_id: outcome.next_event_name
      };

      if (formData.decision_type?.includes('chance')) {
        // For 2-way chance: auto-calculate "else" probability
        let probabilityValue = parseFloat(outcome.probability) || 0.5;
        if (formData.decision_type.startsWith('2way') && index === 1) {
          // "Else" outcome - calculate as 1 - primary probability
          const primaryProbability = parseFloat(outcomes[0]?.probability) || 0.5;
          probabilityValue = 1 - primaryProbability;
        }

        baseOutcome.conditions = [{
          if: 'Probability',
          is: '==',
          value: probabilityValue
        }];
      } else {
        // Condition-based decision
        const ifValue = outcome.if || 'Attribute';
        const isSqlExpr = typeof ifValue === 'string' && (
          ifValue.toUpperCase().includes('SELECT') ||
          ifValue.toUpperCase().includes('UPDATE') ||
          ifValue.toUpperCase().includes('INSERT') ||
          ifValue.toUpperCase().includes('DELETE') ||
          ifValue.includes('Entity.')
        );

        if (isSqlExpr) {
          // SQL/Entity expressions: compare result to true by default if value not provided
          const operator = outcome.is || '==';
          const hasExplicitValue = outcome.value !== undefined && outcome.value !== '' && outcome.value !== null;
          const expectedValue = hasExplicitValue ? outcome.value : true;
          baseOutcome.conditions = [{
            if: ifValue,
            is: operator,
            value: expectedValue
          }];
        } else {
          // Attribute-based condition
          baseOutcome.conditions = [{
            if: ifValue || 'Attribute',
            name: outcome.name || '',
            is: outcome.is || '==',
            value: outcome.value || ''
          }];
        }
      }

      return baseOutcome;
    });

    return {
      decision_type: formData.decision_type,
      outcomes: convertedOutcomes
    };
  };

  const buildAssignConfig = (stepId) => {
    return {
      assignments: assignments.map((assignment) => {
        const base = { assignment_type: assignment.assignment_type };
        if (assignment.assignment_type === 'sql') {
          const out = { ...base, expression: assignment.expression || '' };
          // Include attribute_name only if provided (optional for SQL)
          if (assignment.attribute_name) out.attribute_name = assignment.attribute_name;
          return out;
        }
        // For non-SQL, attribute_name is required
        return { ...base, attribute_name: assignment.attribute_name, value: assignment.value };
      })
    };
  };

  const buildCreateConfig = () => {
    let interarrivalTime = null;

    // Only build interarrival config if NOT triggered (Standard mode)
    if (!formData.is_triggered) {
      interarrivalTime = { formula: formData.interarrival_formula || '' };
      if (formData.interarrival_time_unit) {
        interarrivalTime.time_unit = formData.interarrival_time_unit;
      }
    }

    return {
      entity_table: formData.entity_table || '',
      interarrival_time: interarrivalTime,

      max_entities: formData.max_entities === 'n/a' ? 'n/a' : (parseInt(formData.max_entities) || 'n/a')
    };
  };

  const buildTriggerStepConfig = () => {
    const triggerConfig = {
      target_table: formData.target_table || '',
      count: formData.count
    };

    // Only include fk_column if it's not empty
    if (formData.fk_column && formData.fk_column.trim() !== '') {
      triggerConfig.fk_column = formData.fk_column.trim();
    }

    return triggerConfig;
  };

  const generateStepId = (stepType, formData) => {
    // In the new system, step_id IS the display name
    // So we use formData.name directly as the step_id
    const stepName = formData.name;

    if (!stepName || stepName.trim() === '') {
      // Fallback to auto-generated name if empty
      if (stepType === 'create') {
        const entityTable = formData.entity_table || 'entities';
        return `Create ${entityTable}`;
      }
      return `${stepType.charAt(0).toUpperCase() + stepType.slice(1)} Step`;
    }

    // Return the name as-is (it's already validated in the UI)
    return stepName.trim();
  };

  const getExistingStepIds = () => {
    if (!parsedSchema?.event_simulation?.event_flows) return [];
    const flow = parsedSchema.event_simulation.event_flows[0];
    return flow?.steps?.map(s => s.step_id) || [];
  };

  const generateLabel = (stepType, formData, stepId) => {
    // In the new system, step_id is the display name, so use it directly
    return stepId || formData.name || `${stepType.charAt(0).toUpperCase() + stepType.slice(1)} Step`;
  };

  const renderStepEditor = () => {
    if (!node) return null;

    const stepType = node.data.stepConfig?.step_type;
    const availableSteps = getAvailableStepNames();
    const availableAttributes = getAvailableAttributesForCurrentFlow();



    switch (stepType) {
      case 'event':
        return (
          <EventStepEditor
            formData={formData}
            onFormDataChange={handleFormDataChange}
            resourceRequirements={resourceRequirements}
            onResourceRequirementChange={handleResourceRequirementChange}
            onAddResourceRequirement={addResourceRequirement}
            onRemoveResourceRequirement={removeResourceRequirement}
            resourceDefinitions={resourceDefinitions}
            queueDefinitions={queueDefinitions}
            nameValidation={nameValidation}
            bridgeTables={bridgeTables}
          />
        );

      case 'decide':
        return (
          <DecideStepEditor
            formData={formData}
            onFormDataChange={handleFormDataChange}
            outcomes={outcomes}
            onOutcomeChange={handleOutcomeChange}
            onAddOutcome={addOutcome}
            onRemoveOutcome={removeOutcome}
            availableSteps={availableSteps}
            availableAttributes={availableAttributes}
            nameValidation={nameValidation}
          />
        );

      case 'assign':
        return (
          <AssignStepEditor
            formData={formData}
            onFormDataChange={handleFormDataChange}
            assignments={assignments}
            onAssignmentChange={handleAssignmentChange}
            onAddAssignment={addAssignment}
            onRemoveAssignment={removeAssignment}
            availableAttributes={availableAttributes}
            nameValidation={nameValidation}
          />
        );

      case 'release':
        return (
          <ReleaseStepEditor
            formData={formData}
            onFormDataChange={handleFormDataChange}
            nameValidation={nameValidation}
          />
        );

      case 'create':
        return (
          <CreateStepEditor
            formData={formData}
            onFormDataChange={handleFormDataChange}
            availableSteps={availableSteps}
            availableEntityTables={entityTables}
            nameValidation={nameValidation}
            stepTypes={stepTypes}
          />
        );

      case 'trigger':
        return (
          <TriggerStepEditor
            formData={formData}
            onFormDataChange={handleFormDataChange}
            availableSteps={availableSteps}
            availableTargetTables={availableTargetTables}
            nameValidation={nameValidation}
          />
        );

      default:
        return null;
    }
  };

  // Determine modal size based on step type complexity
  const getModalSize = () => {
    const stepType = node?.data?.stepConfig?.step_type;
    switch (stepType) {
      case 'release':
        return undefined; // Default modal size for single input field
      case 'trigger':
        return 'md'; // Medium size for trigger steps
      case 'create':
      case 'assign':
        return 'lg'; // Large size for complex steps
      case 'event':
      case 'decide':
        return 'lg'; // Keep large for complex editors with tables
      default:
        return 'md'; // Default to medium
    }
  };

  return (
    <>
      <Modal show={show} onHide={onHide} centered backdrop="static" size={getModalSize()} className="step-editor-modal">
        <Modal.Header closeButton>
          <Modal.Title>Edit {node?.data.stepConfig?.step_type || 'Step'} Step</Modal.Title>
        </Modal.Header>
        <Modal.Body style={{ maxHeight: '70vh', overflowY: 'auto' }}>
        {formData._initializedForNode === node?.id ? (
          renderStepEditor()
        ) : (
          <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '300px' }}>
            <span className="text-muted">Loading configuration...</span>
          </div>
        )}
      </Modal.Body>
      <Modal.Footer>
          {node && (
            <Button
              variant="outline-danger"
              onClick={handleDelete}
              className="me-auto"
            >
              <FiTrash2 className="me-2" /> Delete Step
            </Button>
          )}
          <Button
            variant="primary"
            onClick={handleSaveAndClose}
            disabled={!nameValidation.valid}
            title={!nameValidation.valid ? nameValidation.error : 'Save & Close'}
          >
            Save & Close
          </Button>
        </Modal.Footer>
      </Modal>

    </>
  );
};

export default NodeEditModal;
