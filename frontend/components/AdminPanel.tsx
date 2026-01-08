
import React, { useState } from 'react';
import { User, Batch } from '../types';
import { translations, Language } from '../translations';
import { createUser } from '../api';

interface AdminPanelProps {
  users: User[];
  batches: Batch[];
  onUpdateUserCredits: (userId: string, newCredits: number) => void;
  onCreateUser?: () => void; // 用户创建成功后的回调
  lang: Language;
}

export const AdminPanel: React.FC<AdminPanelProps> = ({ users, batches, onUpdateUserCredits, onCreateUser, lang }) => {
  const t = translations[lang];
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<number>(0);
  const [showCreateUserModal, setShowCreateUserModal] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newCredits, setNewCredits] = useState(100);
  const [isCreating, setIsCreating] = useState(false);

  // 计算非admin用户的任务总数和视频总数
  const nonAdminUserIds = new Set(users.filter(u => !u.isAdmin).map(u => u.id));
  const nonAdminBatches = batches.filter(b => nonAdminUserIds.has(b.userId));
  const nonAdminBatchesCount = nonAdminBatches.length;
  const nonAdminVideosCount = nonAdminBatches.reduce((sum, batch) => sum + (batch.imageCount || 0), 0);


  const startEditing = (user: User) => {
    setEditingUserId(user.id);
    setEditValue(user.credits);
  };

  const saveEdit = () => {
    if (editingUserId) {
      onUpdateUserCredits(editingUserId, editValue);
      setEditingUserId(null);
    }
  };

  const handleCreateUser = async () => {
    if (!newUsername.trim()) {
      alert(t.usernameRequired || 'Username is required');
      return;
    }

    setIsCreating(true);
    try {
      await createUser(newUsername.trim(), newCredits, false);
      setShowCreateUserModal(false);
      setNewUsername('');
      setNewCredits(100);
      if (onCreateUser) {
        onCreateUser();
      }
    } catch (error: any) {
      const errorMsg = error?.detail || error?.message || 'Failed to create user';
      alert(errorMsg);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="space-y-12">
      {/* User Management Section */}
      <section>
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-2xl" style={{ background: 'rgba(144, 220, 225, 0.12)' }}>
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: '#90dce1' }}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            </div>
            <div>
              <h2 className="text-3xl font-semibold text-white tracking-tight">{t.userManagement}</h2>
              <p className="text-sm text-gray-400 mt-1">
                {t.totalTasksByNonAdmin}: <span className="text-[#90dce1] font-semibold">{nonAdminBatchesCount}</span>
                {t.totalVideosByNonAdmin && (
                  <> | {t.totalVideosByNonAdmin}: <span className="text-[#90dce1] font-semibold">{nonAdminVideosCount}</span></>
                )}
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowCreateUserModal(true)}
            className="px-6 py-3 text-white font-semibold rounded-2xl transition-all duration-200 shadow-lg hover:shadow-xl flex items-center gap-2"
            style={{ 
              background: 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
              boxShadow: '0 8px 20px rgba(144, 220, 225, 0.3)'
            }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            {t.createUser || 'Create User'}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {users.map(u => (
            <div key={u.id} className="bg-white/[0.04] backdrop-blur-xl border border-white/[0.08] rounded-3xl p-6 hover:border-white/[0.15] transition-all duration-200 shadow-lg">
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3.5">
                  <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${u.username}`} className="w-12 h-12 rounded-full border border-white/[0.1]" />
                  <div>
                    <p className="font-semibold text-white text-base">{u.username}</p>
                    <p className="text-[11px] text-gray-400 uppercase tracking-wider mt-0.5">{u.isAdmin ? 'Administrator' : 'Standard User'}</p>
                  </div>
                </div>
              </div>

              <div className="flex items-end justify-between">
                <div>
                  <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">{t.balance}</p>
                  <p className="text-3xl font-bold text-white tracking-tight">{u.credits} <span className="text-sm font-normal text-gray-400 ml-1">{t.credits}</span></p>
                </div>
                <button 
                  onClick={() => startEditing(u)}
                  className="px-4 py-2 bg-white/[0.08] hover:bg-white/[0.12] text-white text-xs font-medium rounded-xl transition-all duration-200 border border-white/[0.1] hover:border-white/[0.2]"
                >
                  {t.adjustCredits}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Global Task History */}
      <section>
        <div className="flex items-center gap-4 mb-8">
          <div className="p-3 rounded-2xl" style={{ background: 'rgba(144, 220, 225, 0.12)' }}>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: '#90dce1' }}><path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="9"/></svg>
          </div>
          <h2 className="text-3xl font-semibold text-white tracking-tight">{t.systemHistory}</h2>
        </div>

        <div className="bg-white/[0.04] backdrop-blur-xl border border-white/[0.08] rounded-3xl overflow-hidden shadow-xl">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-white/[0.06] text-gray-300 font-medium">
                <th className="px-8 py-5">{t.user}</th>
                <th className="px-8 py-5">{t.batchNamePrefix}</th>
                <th className="px-8 py-5">{t.videosCount.replace('{count}', '')}</th>
                <th className="px-8 py-5">{t.creditsUsed}</th>
                <th className="px-8 py-5">{t.created}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06]">
              {batches.map(batch => (
                <tr key={batch.id} className="hover:bg-white/[0.04] transition-colors duration-200">
                  <td className="px-8 py-5 flex items-center gap-3">
                    <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${batch.userName}`} className="w-8 h-8 rounded-full border border-white/[0.1]" />
                    <span className="text-white font-medium">{batch.userName}</span>
                  </td>
                  <td className="px-8 py-5 text-gray-300">{batch.name}</td>
                  <td className="px-8 py-5 text-gray-300 font-mono">{batch.imageCount}</td>
                  <td className="px-8 py-5 text-gray-300">
                    {batch.creditsUsed !== undefined && batch.creditsUsed > 0 ? (
                      <span className="font-mono">{batch.creditsUsed} {t.credits}</span>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                  <td className="px-8 py-5 text-gray-400">{new Date(batch.timestamp).toLocaleString()}</td>
                </tr>
              ))}
              {batches.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-8 py-16 text-center text-gray-500 italic">
                    {t.noBatches}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Credit Edit Modal */}
      {editingUserId && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-xl animate-in fade-in duration-200">
          <div className="w-full max-w-sm bg-white/[0.05] backdrop-blur-2xl border border-white/[0.1] rounded-3xl p-10 shadow-2xl">
            <h3 className="text-2xl font-semibold text-white mb-8 tracking-tight">
              {t.setCreditsTitle.replace('{name}', users.find(u => u.id === editingUserId)?.username || '')}
            </h3>
            
            <div className="space-y-6">
              <div className="space-y-3">
                <label className="text-xs text-gray-400 uppercase font-medium tracking-wider">{t.newCreditsLabel}</label>
                <input 
                  type="number"
                  value={editValue}
                  onChange={(e) => setEditValue(parseInt(e.target.value) || 0)}
                  className="w-full bg-white/[0.08] border border-white/[0.12] rounded-2xl px-5 py-4 text-3xl font-bold text-white focus:outline-none transition-all duration-200"
                  style={{ 
                    '--tw-ring-color': 'rgba(144, 220, 225, 0.5)'
                  } as React.CSSProperties}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(144, 220, 225, 0.4)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(144, 220, 225, 0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = '';
                    e.target.style.boxShadow = '';
                  }}
                />
              </div>

              <div className="flex gap-4 pt-2">
                <button 
                  onClick={() => setEditingUserId(null)}
                  className="flex-1 py-3.5 bg-white/[0.08] hover:bg-white/[0.12] text-white font-semibold rounded-2xl transition-all duration-200 border border-white/[0.1] hover:border-white/[0.2]"
                >
                  {t.cancel}
                </button>
                <button 
                  onClick={saveEdit}
                  className="flex-1 py-3.5 text-white font-semibold rounded-2xl transition-all duration-200 shadow-lg hover:shadow-xl"
                  style={{ 
                    background: 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
                    boxShadow: '0 8px 20px rgba(144, 220, 225, 0.3)'
                  }}
                >
                  {t.save}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Create User Modal */}
      {showCreateUserModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-xl animate-in fade-in duration-200">
          <div className="w-full max-w-sm bg-white/[0.05] backdrop-blur-2xl border border-white/[0.1] rounded-3xl p-10 shadow-2xl">
            <h3 className="text-2xl font-semibold text-white mb-8 tracking-tight">
              {t.createUserTitle || 'Create New User'}
            </h3>
            
            <div className="space-y-6">
              <div className="space-y-3">
                <label className="text-xs text-gray-400 uppercase font-medium tracking-wider">
                  {t.username || 'Username'}
                </label>
                <input 
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder={t.usernamePlaceholder || 'Enter username'}
                  className="w-full bg-white/[0.08] border border-white/[0.12] rounded-2xl px-5 py-4 text-white placeholder-gray-500 focus:outline-none transition-all duration-200"
                  style={{ 
                    '--tw-ring-color': 'rgba(144, 220, 225, 0.5)'
                  } as React.CSSProperties}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(144, 220, 225, 0.4)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(144, 220, 225, 0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = '';
                    e.target.style.boxShadow = '';
                  }}
                />
              </div>

              <div className="space-y-3">
                <label className="text-xs text-gray-400 uppercase font-medium tracking-wider">
                  {t.initialCredits || 'Initial Credits'}
                </label>
                <input 
                  type="number"
                  value={newCredits}
                  onChange={(e) => setNewCredits(parseInt(e.target.value) || 0)}
                  min="0"
                  className="w-full bg-white/[0.08] border border-white/[0.12] rounded-2xl px-5 py-4 text-2xl font-bold text-white focus:outline-none transition-all duration-200"
                  style={{ 
                    '--tw-ring-color': 'rgba(144, 220, 225, 0.5)'
                  } as React.CSSProperties}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(144, 220, 225, 0.4)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(144, 220, 225, 0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = '';
                    e.target.style.boxShadow = '';
                  }}
                />
                <p className="text-xs text-gray-500 mt-2">
                  {t.defaultPasswordInfo || 'Default password: 123456'}
                </p>
              </div>

              <div className="flex gap-4 pt-2">
                <button 
                  onClick={() => {
                    setShowCreateUserModal(false);
                    setNewUsername('');
                    setNewCredits(100);
                  }}
                  className="flex-1 py-3.5 bg-white/[0.08] hover:bg-white/[0.12] text-white font-semibold rounded-2xl transition-all duration-200 border border-white/[0.1] hover:border-white/[0.2]"
                  disabled={isCreating}
                >
                  {t.cancel}
                </button>
                <button 
                  onClick={handleCreateUser}
                  disabled={isCreating || !newUsername.trim()}
                  className="flex-1 py-3.5 text-white font-semibold rounded-2xl transition-all duration-200 shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ 
                    background: 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
                    boxShadow: '0 8px 20px rgba(144, 220, 225, 0.3)'
                  }}
                >
                  {isCreating ? (t.creating || 'Creating...') : (t.create || 'Create')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
