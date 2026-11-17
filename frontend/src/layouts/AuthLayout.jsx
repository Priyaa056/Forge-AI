import React from 'react';

function AuthLayout({ children }) {
  return (
    <div className="auth-layout-layout">
      {/* Authentication page layout */}
      <main>
        {children}
      </main>
    </div>
  );
}

export default AuthLayout;
