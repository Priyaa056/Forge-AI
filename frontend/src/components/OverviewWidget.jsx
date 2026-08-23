import React from 'react';

function OverviewWidget() {
  const recentItems = [
    {
      id: 1,
      title: 'Complete project documentation',
      status: 'Completed',
    },
    {
      id: 2,
      title: 'Review frontend design',
      status: 'In Progress',
    },
    {
      id: 3,
      title: 'Create database schema',
      status: 'Pending',
    },
  ];

  return (
    <div className="overview-widget">
      <h2>Recent Tasks</h2>

      <div className="overview-list">
        {recentItems.map((item) => (
          <div className="overview-item" key={item.id}>
            <div className="overview-task">
              <strong>{item.title}</strong>
            </div>

            <span className="overview-status">
              {item.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default OverviewWidget;