import React from 'react';
import { Form } from 'react-bootstrap';

const OrderedListGeneratorEditor = ({ generator, onGeneratorChange }) => {
  // Convert values array to newline-separated string for the textarea
  const valuesText = (generator.values || []).join('\n');

  const handleValuesChange = (e) => {
    // Split by newline, keep empty lines to preserve user formatting while typing
    const values = e.target.value.split('\n');
    // Filter out empty strings only at save time (keep them while editing)
    onGeneratorChange('values', values.filter(v => v.trim() !== ''));
  };

  return (
    <Form.Group className="mb-3">
      <Form.Label>Values (one per line)</Form.Label>
      <Form.Control
        as="textarea"
        rows={6}
        value={valuesText}
        onChange={handleValuesChange}
        placeholder={"Consultant\nSenior Consultant\nManager"}
      />
      <Form.Text className="text-muted">
        Each row gets the next value in order. If there are more rows than values, the list wraps around.
      </Form.Text>
    </Form.Group>
  );
};

export default OrderedListGeneratorEditor;
