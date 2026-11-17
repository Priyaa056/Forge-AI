import React from 'react';
import Navbar from '../components/Navbar.jsx';
import Sidebar from '../components/Sidebar.jsx';
import TaskTable from '../components/TaskTable.jsx';
import TaskFilterBar from '../components/TaskFilterBar.jsx';

function TaskPage() {
  return (
    <div className="task-page-page">
      <h1>TaskPage</h1>
      <p>Management page for Task items</p>
      <Navbar />
      <Sidebar />
      <TaskTable />
      <TaskFilterBar />
      {/* Page state requirements:
        - tasksList
        - filterQuery
      */}
    </div>
  );
}

export default TaskPage;
