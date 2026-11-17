import React from 'react';
import RegisterForm from '../components/RegisterForm.jsx';
import AuthCard from '../components/AuthCard.jsx';

function RegisterPage() {
  return (
    <div className="register-page-page">
      <h1>RegisterPage</h1>
      <p>User account registration page</p>
      <RegisterForm />
      <AuthCard />
      {/* Page state requirements:
        - registrationData
        - validationErrors
      */}
    </div>
  );
}

export default RegisterPage;
