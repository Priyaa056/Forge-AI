import React, { useState } from 'react';

function Sidebar({ activePath }) {
  const [isCollapsed, setIsCollapsed] = useState("false");
  const onNavigate = (event) => {
    // Handler for onNavigate
  };
  return (
    <div className="sidebar-container">
      <h3>Sidebar</h3>
    </div>
  );
}

export default Sidebar;
