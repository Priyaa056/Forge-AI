import React from 'react';
import Navbar from '../components/Navbar.jsx';
import Sidebar from '../components/Sidebar.jsx';
import StatsCard from '../components/StatsCard.jsx';

function DashboardPage() {
  return (
    <div className="dashboard-page-page">
      <h1>DashboardPage</h1>
      <p>Main dashboard summary overview for TaskFlow</p>
      <Navbar />
      <Sidebar />
      <StatsCard />
      {/* Page state requirements:
        - currentUser
        - metrics
      */}
    </div>
  );
}

export default DashboardPage;
