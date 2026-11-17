import React, { useState } from 'react';

function UserTable({ items }) {
  const [sortColumn, setSortColumn] = useState("'id'");
  const handleSort = (event) => {
    // Handler for handleSort
  };
  const handleSelectRow = (event) => {
    // Handler for handleSelectRow
  };
  return (
    <div className="user-table-container">
      <h3>UserTable</h3>
    </div>
  );
}

export default UserTable;
