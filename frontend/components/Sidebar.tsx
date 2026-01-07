
import React from 'react';
import { Batch, ViewState } from '../types';
import { translations, Language } from '../translations';

interface SidebarProps {
  batches: Batch[];
  onSelectBatch: (id: string) => void;
  onNewProject: () => void;
  onOpenAdmin: () => void;
  onLogout: () => void;
  selectedId: string | null;
  lang: Language;
  setLang: (lang: Language) => void;
  credits: number;
  username: string;
  isAdmin: boolean;
  currentView: ViewState;
}

export const Sidebar: React.FC<SidebarProps> = ({ 
  batches, 
  onSelectBatch, 
  onNewProject, 
  onOpenAdmin,
  onLogout,
  selectedId, 
  lang, 
  setLang,
  credits,
  username,
  isAdmin,
  currentView
}) => {
  const t = translations[lang];

  return (
    <aside className="w-64 md:w-72 border-r border-white/[0.06] flex flex-col bg-black/40 backdrop-blur-2xl shrink-0">
      <div className="p-6">
        <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-lg" style={{ background: 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)', color: '#000' }}>V</div>
            <span className="text-xl font-semibold tracking-tight text-white">{t.brand}</span>
          </div>
          <button 
            onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
            className="text-[11px] font-medium px-3 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.12] border border-white/[0.1] text-gray-400 hover:text-white transition-all duration-200"
          >
            {lang === 'zh' ? 'EN' : '中文'}
          </button>
        </div>

        {/* Admin Navigation */}
        {isAdmin && (
          <button 
            onClick={onOpenAdmin}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-2xl mb-6 transition-all duration-200 ${
              currentView === 'admin' 
              ? 'bg-[#90dce1]/20 text-[#90dce1] border border-[#90dce1]/30 shadow-lg shadow-[#90dce1]/10' 
              : 'bg-white/[0.06] text-gray-400 border border-white/[0.08] hover:bg-white/[0.1] hover:text-white hover:border-white/[0.15]'
            }`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span className="text-sm font-medium">{t.adminPanel}</span>
          </button>
        )}

        {/* Balance Card */}
        <div className="bg-gradient-to-br from-[#90dce1]/15 to-[#6fc4cc]/10 border border-[#90dce1]/20 rounded-3xl p-5 mb-8 backdrop-blur-xl">
           <p className="text-[11px] text-gray-400 uppercase font-medium tracking-wider mb-2">{t.balance}</p>
           <div className="text-3xl font-bold text-white tracking-tight">{credits} <span className="text-sm font-normal text-gray-400 ml-1">{t.credits}</span></div>
        </div>
        
        <button 
          onClick={onNewProject}
          className={`w-full flex items-center justify-center gap-2.5 font-medium py-3.5 px-4 rounded-2xl transition-all duration-200 mb-8 ${
            currentView === 'create' 
            ? 'bg-white text-black shadow-lg shadow-white/10' 
            : 'bg-white/[0.08] text-white hover:bg-white/[0.12] border border-white/[0.1] hover:border-white/[0.2]'
          }`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
          {t.newBatch}
        </button>

        <div className="space-y-2">
          <h3 className="px-3 text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-3">{t.history}</h3>
          <div className="overflow-y-auto max-h-[calc(100vh-420px)] pr-2 -mr-2 space-y-1.5">
            {batches.length === 0 ? (
              <p className="px-3 text-sm text-gray-500 italic">{t.noBatches}</p>
            ) : (
              batches.map(batch => (
                <button
                  key={batch.id}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onSelectBatch(batch.id);
                  }}
                  className={`w-full text-left px-3.5 py-3 rounded-xl text-sm transition-all duration-200 flex flex-col gap-1 ${
                    selectedId === batch.id 
                      ? 'bg-[#90dce1]/15 text-[#90dce1] border border-[#90dce1]/25 shadow-sm shadow-[#90dce1]/5' 
                      : 'text-gray-400 hover:bg-white/[0.06] hover:text-white border border-transparent'
                  }`}
                >
                  <span className="font-medium truncate">{batch.name}</span>
                  <span className="text-[11px] opacity-70">
                    {new Date(batch.timestamp).toLocaleDateString()} • {batch.imageCount}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="mt-auto p-5 border-t border-white/[0.06] bg-black/20 backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 overflow-hidden">
            <img src={`https://api.dicebear.com/7.x/initials/svg?seed=${username}`} alt="Avatar" className="w-10 h-10 rounded-full bg-white/[0.1] border border-white/[0.1]" />
            <div className="overflow-hidden">
              <p className="text-sm font-medium text-white truncate">{username}</p>
              <p className="text-[11px] text-gray-500">{t.proPlan}</p>
            </div>
          </div>
          <button 
            onClick={onLogout}
            className="p-2 text-gray-500 hover:text-red-400 transition-colors rounded-lg hover:bg-white/[0.06]"
            title={t.logout}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg>
          </button>
        </div>
      </div>
    </aside>
  );
};
