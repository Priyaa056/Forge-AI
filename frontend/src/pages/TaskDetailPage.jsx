import React from 'react';
import Navbar from '../components/Navbar.jsx';
import Sidebar from '../components/Sidebar.jsx';
import TaskDetail from '../components/TaskDetail.jsx';
import TaskForm from '../components/TaskForm.jsx';

function TaskDetailPage() {
  return (
    <div className="task-detail-page-page">
      <h1>TaskDetailPage</h1>
      <p>Detailed view and editor for Task</p>
      <Navbar />
      <Sidebar />
      <TaskDetail />
      <TaskForm />
      {/* Page state requirements:
        - selectedTask
        - isEditing
      */}
    </div>
  );
}

export default TaskDetailPage;
