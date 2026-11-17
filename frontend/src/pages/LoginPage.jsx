import React from 'react';
import LoginForm from '../components/LoginForm.jsx';
import AuthCard from '../components/AuthCard.jsx';

function LoginPage() {
  return (
    <div className="login-page-page">
      <h1>LoginPage</h1>
      <p>User authentication login page</p>
      <LoginForm />
      <AuthCard />
      {/* Page state requirements:
        - loginCredentials
        - authError
      */}
    </div>
  );
}

export default LoginPage;
