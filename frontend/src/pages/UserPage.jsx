import React from 'react';
import Navbar from '../components/Navbar.jsx';
import Sidebar from '../components/Sidebar.jsx';
import UserTable from '../components/UserTable.jsx';
import UserFilterBar from '../components/UserFilterBar.jsx';

function UserPage() {
  return (
    <div className="user-page-page">
      <h1>UserPage</h1>
      <p>Management page for User items</p>
      <Navbar />
      <Sidebar />
      <UserTable />
      <UserFilterBar />
      {/* Page state requirements:
        - usersList
        - filterQuery
      */}
    </div>
  );
}

export default UserPage;
