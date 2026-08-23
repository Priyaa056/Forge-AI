import React from 'react';
import Navbar from '../components/Navbar.jsx';
import Sidebar from '../components/Sidebar.jsx';
import UserDetail from '../components/UserDetail.jsx';
import UserForm from '../components/UserForm.jsx';

function UserDetailPage() {
  return (
    <div className="user-detail-page-page">
      <h1>UserDetailPage</h1>
      <p>Detailed view and editor for User</p>
      <Navbar />
      <Sidebar />
      <UserDetail />
      <UserForm />
      {/* Page state requirements:
        - selectedUser
        - isEditing
      */}
    </div>
  );
}

export default UserDetailPage;
