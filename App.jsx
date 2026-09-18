import React, { useState } from 'react';

export default function App() {
  const [student] = useState({
    name: 'Alex',
    stars: 145,
    level: 'Silver',
    progress: {
      'Fractions': { completed: 5, total: 20, score: 85, stars: 12 },
      'Ratio': { completed: 3, total: 15, score: 78, stars: 9 },
      'Photosynthesis': { completed: 2, total: 10, score: 90, stars: 14 },
      'Grammar': { completed: 4, total: 20, score: 72, stars: 8 }
    },
    badges: ['First Steps', 'Math Master', 'Science Explorer']
  });

  const levels = {
    'Bronze': { threshold: 0, emoji: '🥉' },
    'Silver': { threshold: 100, emoji: '🥈' },
    'Gold': { threshold: 300, emoji: '🥇' },
    'Platinum': { threshold: 500, emoji: '💎' }
  };

  return (
    <div style={{ fontFamily: 'Arial, sans-serif', background: '#f5f7fa', minHeight: '100vh', padding: '20px' }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
        
        {/* Header */}
        <div style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white', padding: '30px', borderRadius: '10px', marginBottom: '30px' }}>
          <h1 style={{ margin: '0 0 10px 0', fontSize: '32px' }}>📚 My Pals Tutor Dashboard</h1>
          <p style={{ margin: 0, fontSize: '16px' }}>Welcome back, <strong>{student.name}</strong>!</p>
        </div>

        {/* Stats Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px', marginBottom: '30px' }}>
          
          {/* Stars */}
          <div style={{ background: 'white', padding: '20px', borderRadius: '10px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 15px 0', color: '#333' }}>⭐ Your Stars</h3>
            <div style={{ fontSize: '48px', fontWeight: 'bold', color: '#FFD700', marginBottom: '10px' }}>{student.stars}</div>
            <p style={{ margin: 0, color: '#666', fontSize: '14px' }}>155 more to reach Gold</p>
          </div>

          {/* Level */}
          <div style={{ background: 'white', padding: '20px', borderRadius: '10px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 15px 0', color: '#333' }}>🏅 Current Level</h3>
            <div style={{ fontSize: '48px', marginBottom: '10px' }}>🥈</div>
            <p style={{ margin: 0, fontSize: '20px', fontWeight: 'bold', color: '#C0C0C0' }}>Silver</p>
          </div>

          {/* Topics */}
          <div style={{ background: 'white', padding: '20px', borderRadius: '10px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 15px 0', color: '#333' }}>📚 Topics Done</h3>
            <div style={{ fontSize: '48px', fontWeight: 'bold', color: '#FF6B6B', marginBottom: '10px' }}>
              {Object.keys(student.progress).length}
            </div>
            <p style={{ margin: 0, color: '#666', fontSize: '14px' }}>Keep it up!</p>
          </div>
        </div>

        {/* Progress */}
        <div style={{ background: 'white', padding: '25px', borderRadius: '10px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)', marginBottom: '30px' }}>
          <h2 style={{ margin: '0 0 20px 0', color: '#333' }}>📊 Progress by Topic</h2>
          
          {Object.entries(student.progress).map(([topic, data]) => (
            <div key={topic} style={{ marginBottom: '20px', paddingBottom: '20px', borderBottom: '1px solid #eee' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontWeight: 'bold', color: '#333' }}>{topic}</span>
                <span style={{ color: '#667eea', fontWeight: 'bold' }}>{data.completed}/{data.total} done</span>
              </div>
              
              <div style={{ background: '#e0e0e0', height: '8px', borderRadius: '4px', marginBottom: '8px', overflow: 'hidden' }}>
                <div style={{
                  background: 'linear-gradient(90deg, #667eea, #764ba2)',
                  height: '100%',
                  width: `${(data.completed / data.total) * 100}%`
                }}></div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#666' }}>
                <span>Score: {data.score}%</span>
                <span>⭐ {data.stars} stars</span>
              </div>
            </div>
          ))}
        </div>

        {/* Badges */}
        <div style={{ background: 'white', padding: '25px', borderRadius: '10px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)', marginBottom: '30px' }}>
          <h2 style={{ margin: '0 0 20px 0', color: '#333' }}>🎖️ Badges</h2>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '15px' }}>
            {student.badges.map((badge, idx) => (
              <div key={idx} style={{
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                color: 'white',
                padding: '20px',
                borderRadius: '10px',
                textAlign: 'center',
                fontSize: '14px',
                fontWeight: 'bold'
              }}>
                {badge}
              </div>
            ))}
          </div>
        </div>

        {/* Level Progression */}
        <div style={{ background: 'white', padding: '25px', borderRadius: '10px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
          <h2 style={{ margin: '0 0 20px 0', color: '#333' }}>🚀 Level Progression</h2>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: '32px', marginBottom: '5px' }}>🥉</div>
              <p style={{ margin: 0, fontSize: '12px', color: '#999' }}>Bronze</p>
            </div>
            <div style={{ flex: 1, height: '4px', background: '#e0e0e0', margin: '0 10px' }}></div>
            
            <div style={{ textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: '32px', marginBottom: '5px' }}>🥈</div>
              <p style={{ margin: 0, fontSize: '12px', color: '#667eea', fontWeight: 'bold' }}>Silver (NOW)</p>
            </div>
            <div style={{ flex: 1, height: '4px', background: '#e0e0e0', margin: '0 10px' }}></div>
            
            <div style={{ textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: '32px', marginBottom: '5px' }}>🥇</div>
              <p style={{ margin: 0, fontSize: '12px', color: '#999' }}>Gold (300⭐)</p>
            </div>
            <div style={{ flex: 1, height: '4px', background: '#e0e0e0', margin: '0 10px' }}></div>
            
            <div style={{ textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: '32px', marginBottom: '5px' }}>💎</div>
              <p style={{ margin: 0, fontSize: '12px', color: '#999' }}>Platinum (500⭐)</p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{ textAlign: 'center', marginTop: '40px', color: '#999', fontSize: '12px' }}>
          <p>My Pals Tutor Bot © 2026 | Keep learning! 📚</p>
        </div>
      </div>
    </div>
  );
}
