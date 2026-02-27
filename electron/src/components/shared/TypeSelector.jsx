import React, { useState, useRef, useEffect } from 'react';
import { Form } from 'react-bootstrap';
import { FiEdit3, FiChevronDown, FiCheck, FiX, FiChevronRight } from 'react-icons/fi';

// Unified type definitions with optional subtypes
const typeCategories = {
  'Numeric': {
    integer: {
      display: 'Integer', template: 'integer', subtypes: {
        int: { display: 'INT', template: 'int' },
        bigint: { display: 'BIGINT', template: 'bigint' },
        smallint: { display: 'SMALLINT', template: 'smallint' },
        tinyint: { display: 'TINYINT', template: 'tinyint' },
      }
    },
    decimal: {
      display: 'Decimal', template: 'decimal(10,2)', subtypes: {
        numeric: { display: 'NUMERIC', template: 'numeric(10,2)' },
      }
    },
    float: {
      display: 'Float', template: 'float', subtypes: {
        double: { display: 'DOUBLE', template: 'double' },
        real: { display: 'REAL', template: 'real' },
      }
    },
    boolean: {
      display: 'Boolean', template: 'boolean', subtypes: {
        bool: { display: 'BOOL', template: 'bool' },
      }
    },
  },
  'String': {
    string: {
      display: 'String', template: 'string', subtypes: {
        varchar: { display: 'VARCHAR', template: 'varchar(255)' },
        char: { display: 'CHAR', template: 'char(1)' },
      }
    },
    text: { display: 'Text', template: 'text' },
  },
  'Temporal': {
    datetime: {
      display: 'DateTime', template: 'datetime', subtypes: {
        timestamp: { display: 'TIMESTAMP', template: 'timestamp' },
      }
    },
    date: { display: 'Date', template: 'date' },
    time: { display: 'Time', template: 'time' },
  },
  'System': {
    pk: { display: 'Primary Key', template: 'pk' },
    fk: { display: 'Foreign Key', template: 'fk' },
    entity_id: { display: 'Entity ID (FK)', template: 'entity_id' },
    resource_id: { display: 'Resource ID (FK)', template: 'resource_id' },
    event_type: { display: 'Event Type', template: 'event_type' },
    resource_type: { display: 'Resource Type', template: 'resource_type' },
  }
};

// Build flat lookup of all types (including subtypes) for display resolution
const buildAllTypes = () => {
  const all = {};
  Object.values(typeCategories).forEach(category => {
    Object.entries(category).forEach(([key, info]) => {
      all[key] = info;
      if (info.subtypes) {
        Object.entries(info.subtypes).forEach(([subKey, subInfo]) => {
          all[subKey] = subInfo;
        });
      }
    });
  });
  return all;
};

const allTypes = buildAllTypes();

const TypeSelector = ({
  value = 'string',
  onChange,
  size = 'sm',
  disabled = false,
  className = '',
  placeholder = 'Select type'
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [expandedParent, setExpandedParent] = useState(null);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0, width: 0 });
  const dropdownRef = useRef(null);
  const inputRef = useRef(null);

  const isParameterizedValue = (typeValue) => {
    return typeValue && typeValue.includes('(') && typeValue.includes(')');
  };

  const getBaseType = (typeValue) => {
    if (isParameterizedValue(typeValue)) {
      return typeValue.split('(')[0];
    }
    return typeValue;
  };

  useEffect(() => {
    setEditValue(value);
  }, [value]);

  const calculateDropdownPosition = () => {
    if (dropdownRef.current) {
      const rect = dropdownRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + window.scrollY + 2,
        left: rect.left + window.scrollX,
        width: Math.max(rect.width, 200)
      });
    }
  };

  const handleTypeSelect = (typeKey, typeInfo) => {
    setDropdownOpen(false);
    setExpandedParent(null);

    if (isParameterizedValue(typeInfo.template)) {
      setEditValue(typeInfo.template);
      setIsEditing(true);
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          inputRef.current.select();
        }
      }, 0);
    } else {
      onChange(typeInfo.template);
    }
  };

  const handleToggleExpand = (e, typeKey) => {
    e.stopPropagation();
    setExpandedParent(prev => prev === typeKey ? null : typeKey);
  };

  const handleEditClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setEditValue(value);
    setIsEditing(true);
    setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus();
        inputRef.current.select();
      }
    }, 0);
  };

  const handleInputChange = (e) => {
    setEditValue(e.target.value);
  };

  const handleSaveEdit = () => {
    onChange(editValue);
    setIsEditing(false);
  };

  const handleCancelEdit = () => {
    setEditValue(value);
    setIsEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSaveEdit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleCancelEdit();
    }
  };

  const getDisplayText = () => {
    if (!value) return placeholder;

    for (const [key, typeInfo] of Object.entries(allTypes)) {
      if (typeInfo.template === value) {
        return typeInfo.display;
      }
    }

    if (isParameterizedValue(value)) {
      return value;
    }

    return value;
  };

  // Check if a value matches a type or any of its subtypes
  const isActiveType = (typeKey, typeInfo) => {
    const baseVal = getBaseType(value);
    if (baseVal === typeKey) return true;
    if (typeInfo.subtypes) {
      return Object.keys(typeInfo.subtypes).includes(baseVal);
    }
    return false;
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        const menu = document.querySelector('.type-selector-menu');
        if (menu && menu.contains(event.target)) return;
        setDropdownOpen(false);
        setExpandedParent(null);
      }
    };

    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [dropdownOpen]);

  if (disabled) {
    return (
      <Form.Control
        type="text"
        value={getDisplayText()}
        readOnly
        size={size}
        className={`form-control-readonly ${className}`}
      />
    );
  }

  if (isEditing) {
    return (
      <div className={`type-selector type-selector-editing ${className}`}>
        <div className={`type-selector-input ${size === 'sm' ? 'type-selector-input-sm' : ''}`}>
          <input
            ref={inputRef}
            type="text"
            value={editValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            className="type-selector-edit-field"
            placeholder="Enter type (e.g., decimal(10,2))"
          />
          <button
            type="button"
            className="type-selector-icon-btn type-selector-save-icon"
            onClick={handleSaveEdit}
            title="Save type (Enter)"
          >
            <FiCheck size={12} />
          </button>
          <button
            type="button"
            className="type-selector-icon-btn type-selector-cancel-icon"
            onClick={handleCancelEdit}
            title="Cancel edit (Escape)"
          >
            <FiX size={12} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`type-selector ${className}`} ref={dropdownRef}>
      <div className={`type-selector-input ${size === 'sm' ? 'type-selector-input-sm' : ''}`}>
        <button
          type="button"
          className="type-selector-icon-btn type-selector-edit-icon"
          onClick={handleEditClick}
          title="Edit type manually"
        >
          <FiEdit3 size={10} />
        </button>

        <span className="type-selector-value">{getDisplayText()}</span>

        <button
          type="button"
          className="type-selector-icon-btn type-selector-dropdown-icon"
          onClick={() => {
            if (!dropdownOpen) {
              calculateDropdownPosition();
            }
            setDropdownOpen(!dropdownOpen);
            if (dropdownOpen) setExpandedParent(null);
          }}
          title="Select from templates"
        >
          <FiChevronDown
            size={10}
            className={`chevron ${dropdownOpen ? 'chevron-up' : ''}`}
          />
        </button>
      </div>

      {dropdownOpen && (
        <div
          className="type-selector-menu"
          style={{
            top: `${dropdownPosition.top}px`,
            left: `${dropdownPosition.left}px`,
            width: `${dropdownPosition.width}px`
          }}
        >
          {Object.entries(typeCategories).map(([categoryName, types], catIndex) => (
            <React.Fragment key={categoryName}>
              <div className="dropdown-header">{categoryName}</div>
              {Object.entries(types).map(([typeKey, typeInfo]) => (
                <div key={typeKey} className="type-selector-item-group">
                  <div className="dropdown-item-row">
                    <button
                      type="button"
                      className={`dropdown-item ${isActiveType(typeKey, typeInfo) ? 'active' : ''}`}
                      onClick={() => handleTypeSelect(typeKey, typeInfo)}
                    >
                      {typeInfo.display}
                      {isParameterizedValue(typeInfo.template) && (
                        <span className="text-muted ms-1">
                          ({typeInfo.template.split('(')[1].replace(')', '')})
                        </span>
                      )}
                    </button>
                    {typeInfo.subtypes && (
                      <button
                        type="button"
                        className={`type-selector-expand-btn ${expandedParent === typeKey ? 'expanded' : ''}`}
                        onClick={(e) => handleToggleExpand(e, typeKey)}
                        title="Show variants"
                      >
                        <FiChevronRight size={10} />
                      </button>
                    )}
                  </div>

                  {typeInfo.subtypes && expandedParent === typeKey && (
                    <div className="type-selector-subtypes">
                      {Object.entries(typeInfo.subtypes).map(([subKey, subInfo]) => (
                        <button
                          key={subKey}
                          type="button"
                          className={`dropdown-item subtype-item ${getBaseType(value) === subKey ? 'active' : ''}`}
                          onClick={() => handleTypeSelect(subKey, subInfo)}
                        >
                          {subInfo.display}
                          {isParameterizedValue(subInfo.template) && (
                            <span className="text-muted ms-1">
                              ({subInfo.template.split('(')[1].replace(')', '')})
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {catIndex < Object.keys(typeCategories).length - 1 && <div className="dropdown-divider" />}
            </React.Fragment>
          ))}

          <div className="dropdown-divider" />
          <button
            type="button"
            className="dropdown-item text-primary"
            onClick={handleEditClick}
          >
            <FiEdit3 className="me-1" />
            Custom Type...
          </button>
        </div>
      )}
    </div>
  );
};

export default TypeSelector;
