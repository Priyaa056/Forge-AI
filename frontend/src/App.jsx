import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import DashboardPage from './pages/DashboardPage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import RegisterPage from './pages/RegisterPage.jsx';
import UserPage from './pages/UserPage.jsx';
import UserDetailPage from './pages/UserDetailPage.jsx';
import TaskPage from './pages/TaskPage.jsx';
import TaskDetailPage from './pages/TaskDetailPage.jsx';
import CategoryPage from './pages/CategoryPage.jsx';
import CategoryDetailPage from './pages/CategoryDetailPage.jsx';

function App() {
  return (
    <BrowserRouter>
      <div className="app-container">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/users" element={<UserPage />} />
          <Route path="/users/:id" element={<UserDetailPage />} />
          <Route path="/tasks" element={<TaskPage />} />
          <Route path="/tasks/:id" element={<TaskDetailPage />} />
          <Route path="/categories" element={<CategoryPage />} />
          <Route path="/categories/:id" element={<CategoryDetailPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
