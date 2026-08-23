import React from 'react';
import Navbar from '../components/Navbar.jsx';
import Sidebar from '../components/Sidebar.jsx';
import CategoryTable from '../components/CategoryTable.jsx';
import CategoryFilterBar from '../components/CategoryFilterBar.jsx';

function CategoryPage() {
  return (
    <div className="category-page-page">
      <h1>CategoryPage</h1>
      <p>Management page for Category items</p>
      <Navbar />
      <Sidebar />
      <CategoryTable />
      <CategoryFilterBar />
      {/* Page state requirements:
        - categoriesList
        - filterQuery
      */}
    </div>
  );
}

export default CategoryPage;
