import React, { useEffect, useRef } from 'react';

// Minimal code block wrapper matching existing styles
const CodeBlock = ({ children }) => (
  <div className="code-example">
    <pre>
      <code>{children}</code>
    </pre>
  </div>
);

// Standalone overlay that renders the README content verbatim
const GuideOverlay = React.memo(({ visible, onClose, activeSection }) => {
  const overlayRef = useRef(null);
  const contentRef = useRef(null);
  const PUBLIC_URL = (typeof process !== 'undefined' && process.env && process.env.PUBLIC_URL) ? process.env.PUBLIC_URL : 'public';

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    if (visible) document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [visible, onClose]);

  // Scroll to active section within the overlay content when set
  useEffect(() => {
    if (!visible || !activeSection) return;
    const container = contentRef.current;
    const safeId = (typeof CSS !== 'undefined' && CSS.escape) ? CSS.escape(activeSection) : activeSection;
    const target = container?.querySelector(`#${safeId}`);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [visible, activeSection]);

  if (!visible) return null;

  return (
    <div className="guide-overlay-backdrop" onMouseDown={onClose}>
      <div
        ref={overlayRef}
        className="guide-overlay-card"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="guide-overlay-header">
          <button
            type="button"
            className="guide-overlay-close"
            aria-label="Close guide"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <div className="guide-overlay-content" ref={contentRef}>
          <h1 id="relsim">RelSim</h1>
          <p>Database education tool for creating realistic synthetic data across various teaching scenarios.</p>

          {/* Table of Contents moved to NavigationSidebar */}

          <h2 id="database-configuration">Database Configuration</h2>
          <p>Configure database schemas through an intuitive interface to create entities with attributes, relationships, and data generators.</p>

          <p><strong>Database Configuration Dashboard</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/database/database_config_dashboard.png`} alt="Database Configuration Interface" />
          </p>
          <p><em>Main interface showing table creation, relationships, and schema management</em></p>

          <p>Define table types (entity, event, resource, bridging) and configure column properties for your simulation database.</p>

          <h2 id="data-generation-methods">Data Generation Methods</h2>
          <p>Configure data generators for realistic synthetic data creation using multiple approaches.</p>

          <p><strong>Database Entity Editor</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/database/data_table_editor.png`} alt="Data Table Editor" />
          </p>
          <p><em>Double-click any table to access the entity editor for configuring attributes and data generators</em></p>

          <h3 id="fakerjs-generator">Faker.js Generator</h3>
          <p>Generate realistic synthetic data using Faker.js methods for names, addresses, dates, and more.</p>

          <p><strong>Faker Configuration Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/database/faker.png`} alt="Data Generator: Faker" />
          </p>
          <p><em>Interface for selecting Faker.js methods and configuring realistic data generation</em></p>

          <CodeBlock>{`# Example: Faker.js configuration
name: last_name
type: string
generator:
  type: faker
  method: person.lastName`}</CodeBlock>

          <h3 id="distribution-generator">Distribution Generator</h3>
          <p>Create statistically accurate data using mathematical distributions for numerical values.</p>

          <p><strong>Distribution Configuration Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/database/distribution_generator.png`} alt="Distribution Generator" />
          </p>
          <p><em>Configure statistical distributions (UNIF, NORM, EXPO) for numerical data generation</em></p>

          <CodeBlock>{`# Example: Statistical distribution
generator:
  type: distribution
  formula: UNIF(1, 100)  # NORM, EXPO, DISC`}</CodeBlock>

          <h3 id="sql-formula-generator">SQL Formula Generator</h3>
          <p>Generate relationship-aware data using SQL expressions for complex temporal and relational constraints.</p>

          <p><strong>SQL Formula Configuration Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/database/sql_formula_expression.png`} alt="SQL Formula Generator" />
          </p>
          <p><em>Create complex formulas using SQL queries and date arithmetic for dependent data</em></p>

          <CodeBlock>{`# Example: SQL formula with date arithmetic
generator:
  type: formula
  expression: MIN(SELECT created_at FROM Order WHERE customer_id = @id) + DAYS(30)`}</CodeBlock>

          <h2 id="special-tables-and-columns">Special Tables and Columns</h2>

          <h3 id="table-types">Table Types</h3>
          <ul>
            <li><strong>entity</strong>: Primary business objects (Customer, Order)</li>
            <li><strong>event</strong>: Event tracking tables</li>
            <li><strong>resource</strong>: Resource pools (Staff, Equipment)</li>
            <li><strong>bridge</strong>: Many-to-many relationships</li>
          </ul>

          <h3 id="column-types">Column Types</h3>
          <ul>
            <li><strong>event_type</strong>: Event classification column</li>
            <li><strong>entity_type</strong>: Entity classification column</li>
            <li><strong>resource_type</strong>: Resource classification column</li>
            <li><strong>entity_id</strong>: Links to entity tables (fk)</li>
            <li><strong>resource_id</strong>: Resource identifier (fk)</li>
          </ul>

          <h2 id="simulation-configuration">Simulation Configuration</h2>
          <p>Configure simulation parameters, termination conditions, and resource constraints for your discrete event simulation.</p>

          <p><strong>Simulation Dashboard Overview</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/simulation_dashboard.png`} alt="Simulation Dashboard" />
          </p>
          <p><em>Main simulation interface showing flow design, configuration panels, and control buttons</em></p>

          <h3 id="termination-conditions">Termination Conditions</h3>
          <p>Define when your simulation should stop. Access termination settings via the Simulation Settings button in the floating toolbar.</p>

          <p><strong>Simulation Settings Access</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/simulation_setting_in_toolbar.png`} alt="Simulation Setting Button" />
          </p>
          <p><em>Location of the Simulation Settings button in the floating toolbar</em></p>

          <p><strong>Termination Configuration Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/simulation_setting.png`} alt="Simulation Setting" />
          </p>
          <p><em>Configure time-based, entity count, or combined termination conditions</em></p>

          <p><strong>Termination Types:</strong></p>
          <ul>
            <li><strong>Time-based</strong>: <code>TIME(200)</code> - Run for 200 time units</li>
            <li><strong>Entity count</strong>: <code>ENTITIES(Order, 100)</code> - Stop when Order table reaches 100 entities</li>
            <li><strong>Combined conditions</strong>:
              <ul>
                <li><code>TIME(720) OR ENTITIES(Order, 1000)</code> - Stop at either condition</li>
                <li><code>TIME(480) AND ENTITIES(Ticket, 200)</code> - Stop when both conditions are met</li>
              </ul>
            </li>
          </ul>

          <h3 id="resource-configuration">Resource Configuration</h3>
          <p>Define capacity constraints for shared resources (staff, equipment, etc.) that entities compete for during simulation.</p>

          <p><strong>Resource Management Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/resource_editor.png`} alt="Resource Editor" />
          </p>
          <p><em>Main resource configuration panel showing available resource types and capacity settings</em></p>

          <p><strong>Resource Configuration Modal</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/resource_editor_modal.png`} alt="Resource Editor Modal" />
          </p>
          <p><em>Resource setup interface for configuring capacity limits by resource type</em></p>

          <CodeBlock>{`# Example: Staff resource configuration
resources:
  Staff:
    "Tech Support": 2    # 2 tech support staff available
    Developer: 1         # 1 developer available  
    Manager: 1           # 1 manager available`}</CodeBlock>

          <p><strong>Resource Features:</strong></p>
          <ul>
            <li><strong>Fixed capacity</strong>: Set maximum available units per resource type</li>
            <li><strong>FIFO allocation</strong>: Resources allocated first-come, first-served</li>
            <li><strong>Automatic release</strong>: Resources freed when entity completes or reaches Release step</li>
            <li><strong>Blocking behavior</strong>: Entities wait when required resources are unavailable</li>
          </ul>

          <h3 id="entity-configuration">Entity Configuration</h3>
          <p>Define resource consumption and entity attributes for different entity types during simulation.</p>

          <p><strong>Entity Management Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/entity_editor.png`} alt="Entity Editor" />
          </p>
          <p><em>Entity configuration panel showing available entity types</em></p>

          <h2 id="simulation-steps">Simulation Steps</h2>
          <p>Configure workflow steps by double-clicking on flow nodes to open their respective editors.</p>

          <h3 id="create">Create</h3>
          <p>Generate entities with configurable arrival patterns to initiate simulation flows.</p>

          <p><strong>Create Step Configuration Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/create_module.png`} alt="Create Editor" />
          </p>
          <p><em>Configure entity generation, arrival rates, and maximum entity limits</em></p>

          <CodeBlock>{`# Example: Create step configuration
step_type: create
create_config:
  entity_table: Order
  interarrival_time:
    formula: EXPO(2)`}</CodeBlock>

          <h3 id="event">Event</h3>
          <p>Process entities with configurable duration and optional resource requirements.</p>

          <p><strong>Event Step Configuration Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/event_module.png`} alt="Event Editor" />
          </p>
          <p><em>Configure processing duration, resource requirements, and capacity constraints</em></p>

          <CodeBlock>{`# Example: Event step configuration
step_type: event
event_config:
  duration:
    formula: NORM(1, 0.1)
  resource_requirements:
    - resource: Staff
      count: 1`}</CodeBlock>

          <h3 id="assign">Assign</h3>
          <p>Assign new attributes or update database tables during simulation with support for dynamic values.</p>

          <p><strong>Attribute Assignment Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/assign_module.png`} alt="Assign Module" />
          </p>
          <p><em>Configure attribute assignments with static values or dynamic templates</em></p>

          <p><strong>SQL Update Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/assign_sql_backorder.png`} alt="Assign SQL Example" />
          </p>
          <p><em>Execute SQL UPDATE statements to modify any table in the database</em></p>

          <p><strong>Assignment Types:</strong></p>
          <ul>
            <li><strong>Attribute assignment</strong>: Set entity attributes with custom names and values</li>
            <li><strong>SQL updates</strong>: Execute UPDATE statements to modify any table in the database</li>
            <li><strong>Dynamic values</strong>: Use templates like <code>{`{{current_time}}`}</code> or <code>{`{{entity_id}}`}</code> for runtime values</li>
          </ul>

          <CodeBlock>{`# Example: Mixed assignment types
step_type: assign
assign_config:
  assignments:
    - assignment_type: attribute
      attribute_name: status
      value: processed
    - assignment_type: attribute
      attribute_name: completion_time
      value: "{{current_time}}"`}</CodeBlock>

          <h3 id="decide">Decide</h3>
          <p>Route entities using 4 decision types for probability-based or conditional branching.</p>

          <p><strong>Decision Types:</strong></p>
          <ul>
            <li><code>2way-chance</code> - Two-path probability routing (70% approve, 30% reject)</li>
            <li><code>2way-condition</code> - Two-path based on attribute values (if quality_score &gt;= 8)</li>
            <li><code>nway-chance</code> - Multiple paths with explicit probabilities (60%/30%/10%)</li>
            <li><code>nway-condition</code> - Multiple paths based on different attribute conditions</li>
          </ul>

          <p><strong>Attribute Condition Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/decision_module_condition.png`} alt="Decision Module Modal" />
          </p>
          <p><em>Configure attribute-based conditions comparing entity attributes with specified values</em></p>

          <p><strong>SQL Query Condition Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/decision_sql_result,png.png`} alt="Decision Module SQL" />
          </p>
          <p><em>Configure SQL-based conditions for complex database queries</em></p>

          <p><strong>Conditional Decision Features:</strong></p>
          <ul>
            <li><strong>Attribute conditions</strong>: Compare entity attributes (<code>status == "complete"</code>)</li>
            <li><strong>SQL query conditions</strong>: Compare against database results for complex logic</li>
            <li><strong>Supported operators</strong>: <code>==</code>, <code>!=</code>, <code>&gt;</code>, <code>&gt;=</code>, <code>&lt;</code>, <code>&lt;=</code></li>
          </ul>

          <CodeBlock>{`# Example: Probability-based decision
step_type: decide
decide_config:
  decision_type: 2way-chance
  outcomes:
    - outcome_id: approve
      next_step_id: process_approval
      conditions:
        - if: Probability
          is: ==
          value: 0.8
    - outcome_id: reject
      next_step_id: handle_rejection
      conditions: []  # else case`}</CodeBlock>

          <h3 id="release">Release</h3>
          <p>Dispose entities and automatically free all allocated resources to complete the simulation flow.</p>

          <CodeBlock>{`# Example: Release step configuration
step_type: release
# No additional configuration required
# Automatically releases all resources and completes entity journey`}</CodeBlock>

          <h2 id="result-viewer">Result Viewer</h2>
          <p>Review generated database tables and analyze simulation results with integrated data navigation.</p>

          <p><strong>Results Analysis Interface</strong></p>
          <p>
            <img src={`${PUBLIC_URL}/doc/simulation/result_viewer.png`} alt="Results Interface" />
          </p>
          <p><em>Navigate between database tables using the project sidebar and analyze simulation outcomes</em></p>

          <hr />
        </div>
      </div>
    </div>
  );
});

export default GuideOverlay;
