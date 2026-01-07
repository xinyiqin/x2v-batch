
import React, { useState, useCallback, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { BatchForm } from './components/BatchForm';
import { BatchGallery } from './components/BatchGallery';
import { AdminPanel } from './components/AdminPanel';
import { Login } from './components/Login';
import { ChangePasswordModal } from './components/ChangePasswordModal';
import { Batch, ViewState, User } from './types';
import { translations, Language } from './translations';
import { getToken, clearToken, getProfile, getBatches, getAllUsers, getAllBatches } from './api';

const App: React.FC = () => {
  const [activeUser, setActiveUser] = useState<User | null>(null);
  const [allUsers, setAllUsers] = useState<User[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [currentViewState, setCurrentViewState] = useState<ViewState>('create');
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [lang, setLang] = useState<Language>('zh');
  const [showChangePasswordModal, setShowChangePasswordModal] = useState(false);

  const t = translations[lang];

  // 检查登录状态
  useEffect(() => {
    const token = getToken();
    if (token) {
      // 尝试获取用户信息
      getProfile()
        .then(user => {
          setActiveUser(user);
          loadUserBatches(user.id);
        })
        .catch(() => {
          clearToken();
        });
    }
  }, []);

  // 加载用户批次
  const loadUserBatches = async (userId: string) => {
    try {
      const response = await getBatches(50, 0);
      setBatches(response.batches);
    } catch (error) {
      console.error('Failed to load batches:', error);
    }
  };

  // 加载所有用户（管理员）
  const loadAllUsers = async () => {
    try {
      const response = await getAllUsers();
      setAllUsers(response.users);
    } catch (error) {
      console.error('Failed to load users:', error);
    }
  };

  // 同步用户信息
  useEffect(() => {
    if (activeUser) {
      getProfile()
        .then(user => setActiveUser(user))
        .catch(console.error);
    }
  }, [batches]);

  const handleLogin = (user: User) => {
    setActiveUser(user);
    loadUserBatches(user.id);
    if (user.isAdmin) {
      loadAllUsers();
    }
  };

  const handleLogout = () => {
    clearToken();
    setActiveUser(null);
    setCurrentViewState('create');
    setSelectedBatchId(null);
    setBatches([]);
    setAllUsers([]);
  };

  const handleCreateBatch = useCallback((newBatch: Batch) => {
    if (!activeUser) return;
    
    setBatches(prev => [newBatch, ...prev]);
    setSelectedBatchId(newBatch.id);
    setCurrentViewState('gallery');
    
    // 刷新用户信息以更新点数
    getProfile()
      .then(user => setActiveUser(user))
      .catch(console.error);
  }, [activeUser]);

  const handleUpdateUserCredits = async (userId: string, newCredits: number) => {
    try {
      const { updateUserCredits } = await import('./api');
      await updateUserCredits(userId, newCredits);
      await loadAllUsers();
      // 如果更新的是当前用户，刷新当前用户信息
      if (activeUser && activeUser.id === userId) {
        const user = await getProfile();
        setActiveUser(user);
      }
    } catch (error) {
      console.error('Failed to update credits:', error);
      alert('Failed to update credits');
    }
  };

  const handleSelectBatch = useCallback((id: string) => {
    // 立即更新状态，确保 UI 响应
    setSelectedBatchId(id);
    setCurrentViewState('gallery');
    
    // 先检查批次是否在缓存中
    const batch = batches.find(b => b.id === id);
    
    if (!batch && activeUser) {
      // 批次不在缓存中，异步加载数据
      (async () => {
        try {
          const response = await getBatches(50, 0);
          setBatches(response.batches);
          // 检查新加载的数据中是否有该批次
          const foundBatch = response.batches.find(b => b.id === id);
          if (!foundBatch) {
            // 尝试直接获取批次详情
            try {
              const { getBatch } = await import('./api');
              const batchDetail = await getBatch(id);
              setBatches(prev => {
                const exists = prev.find(b => b.id === id);
                if (!exists) {
                  return [batchDetail, ...prev];
                }
                return prev;
              });
            } catch (err) {
              console.error('Failed to fetch batch detail:', err);
            }
          }
        } catch (error) {
          console.error('Failed to reload batches:', error);
        }
      })();
    }
  }, [batches, activeUser]);

  const handleNewProject = useCallback(() => {
    setCurrentViewState('create');
    setSelectedBatchId(null);
  }, []);

  const handleOpenAdmin = useCallback(async () => {
    setCurrentViewState('admin');
    setSelectedBatchId(null);
    // 加载所有用户和批次
    if (activeUser?.isAdmin) {
      try {
        const [usersResponse, batchesResponse] = await Promise.all([
          getAllUsers(),
          getAllBatches(100, 0),
        ]);
        setAllUsers(usersResponse.users);
        setBatches(batchesResponse.batches);
      } catch (error) {
        console.error('Failed to load admin data:', error);
        alert('加载管理数据失败: ' + (error as Error).message);
      }
    }
  }, [activeUser]);

  if (!activeUser) {
    return <Login onLogin={handleLogin} lang={lang} />;
  }

  const selectedBatch = batches.find(b => b.id === selectedBatchId);
  const userBatches = batches.filter(b => b.userId === activeUser.id);
  

  return (
    <div className="flex h-screen overflow-hidden bg-black">
      {/* Sidebar - Persistent navigation */}
      <Sidebar 
        batches={userBatches} 
        onSelectBatch={handleSelectBatch} 
        onNewProject={handleNewProject}
        onOpenAdmin={handleOpenAdmin}
        onLogout={handleLogout}
        onOpenChangePassword={() => setShowChangePasswordModal(true)}
        selectedId={selectedBatchId}
        lang={lang}
        setLang={setLang}
        credits={activeUser.credits}
        username={activeUser.username}
        isAdmin={activeUser.isAdmin}
        currentView={currentViewState}
      />

      {/* Change Password Modal */}
      <ChangePasswordModal
        isOpen={showChangePasswordModal}
        onClose={() => setShowChangePasswordModal(false)}
        lang={lang}
      />

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto bg-black">
        <div className="max-w-7xl mx-auto p-6 md:p-10">
          {currentViewState === 'create' ? (
            <div className="animate-in fade-in duration-500">
              <header className="mb-10">
                <h1 className="text-4xl font-semibold tracking-tight text-white mb-3">{t.createTitle}</h1>
                <p className="text-gray-400 text-base">{t.createSubtitle}</p>
              </header>
              <BatchForm onCreated={handleCreateBatch} lang={lang} userCredits={activeUser.credits} />
            </div>
          ) : currentViewState === 'admin' ? (
            <div className="animate-in slide-in-from-bottom-4 duration-500">
               <AdminPanel 
                 users={allUsers.length > 0 ? allUsers : []} 
                 batches={batches.length > 0 ? batches : []} 
                 lang={lang} 
                 onUpdateUserCredits={handleUpdateUserCredits} 
               />
            </div>
          ) : currentViewState === 'gallery' ? (
            <div className="animate-in slide-in-from-right-4 duration-500">
              {selectedBatchId && selectedBatch ? (
                <BatchGallery key={selectedBatchId} batch={selectedBatch} lang={lang} />
              ) : selectedBatchId ? (
                <div className="text-center text-gray-500 py-20">
                  <p>{t.batchNotFound}</p>
                  <p className="text-sm mt-2">批次 ID: {selectedBatchId}</p>
                  <button 
                    onClick={handleNewProject}
                    className="mt-6 px-6 py-3 text-white font-semibold rounded-2xl transition-all duration-200 shadow-lg hover:shadow-xl"
                    style={{ 
                      background: 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
                      boxShadow: '0 8px 20px rgba(144, 220, 225, 0.3)'
                    }}
                  >
                    {t.createNewBtn}
                  </button>
                </div>
              ) : (
                <div className="text-center text-gray-500 py-20">
                  <p>{t.batchNotFound}</p>
                  <button 
                    onClick={handleNewProject}
                    className="mt-6 px-6 py-3 text-white font-semibold rounded-2xl transition-all duration-200 shadow-lg hover:shadow-xl"
                    style={{ 
                      background: 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
                      boxShadow: '0 8px 20px rgba(144, 220, 225, 0.3)'
                    }}
                  >
                    {t.createNewBtn}
                  </button>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
};

export default App;
