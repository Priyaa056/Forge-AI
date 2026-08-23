import React from 'react';
import CategoryForm from './CategoryForm';

/**
 * CategoryCreateModal Component (modal)
 * Modal dialog popup container for creating a new Category
 */
function CategoryCreateModal({ isOpen, onClose }) {
  const handleClose = (event) => {
    if (event && event.preventDefault) event.preventDefault();
    // Handler implementation placeholder for handleClose
  };
  return (
    <div className="category-create-modal">
      <div className="modal-content">
        <h3>CategoryCreateModal</h3>
        <CategoryForm />
      </div>
    </div>
  );
}

export default CategoryCreateModal;
