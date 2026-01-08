
import React, { useState } from 'react';
import { translations, Language } from '../translations';
import { User } from '../types';
import { login } from '../api';

interface LoginProps {
  onLogin: (user: User) => void;
  lang: Language;
}

export const Login: React.FC<LoginProps> = ({ onLogin, lang }) => {
  const t = translations[lang];
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Please enter username and password');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await login(username, password);
      onLogin(response.user_info);
    } catch (err: any) {
      // 提取错误信息，优先使用详细错误，如果没有则使用通用错误
      let errorMessage = 'Login failed';
      if (err.message) {
        errorMessage = err.message;
      } else if (err.detail) {
        errorMessage = err.detail;
      }
      
      // 根据语言显示错误信息
      if (lang === 'zh') {
        if (errorMessage.includes('Invalid username or password') || errorMessage.includes('401')) {
          errorMessage = '用户名或密码错误';
        } else if (errorMessage.includes('User not found')) {
          errorMessage = '用户不存在';
        } else if (errorMessage.includes('HTTP')) {
          errorMessage = '登录失败，请稍后重试';
        }
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-black p-4">
      <div className="w-full max-w-md animate-in fade-in zoom-in duration-500">
        <div className="flex flex-col items-center mb-12">
          <div className="w-20 h-20 rounded-3xl flex items-center justify-center text-4xl font-bold mb-6 shadow-2xl" style={{ background: 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)', color: '#000' }}>V</div>
          <h1 className="text-4xl font-semibold text-white mb-2 tracking-tight">{t.loginTitle}</h1>
          <p className="text-gray-400 text-sm">{t.loginSubtitle}</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-5 bg-white/[0.05] backdrop-blur-2xl p-10 rounded-3xl border border-white/[0.1] shadow-2xl">
          <div className="space-y-2.5">
            <label className="text-sm font-medium text-gray-300">{t.username}</label>
            <input 
              type="text" 
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-white/[0.08] border border-white/[0.12] rounded-2xl px-5 py-3.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#90dce1]/50 focus:border-[#90dce1]/30 transition-all duration-200"
              placeholder={t.usernamePlaceholder || t.username}
              required
            />
          </div>
          <div className="space-y-2.5">
            <label className="text-sm font-medium text-gray-300">{t.password}</label>
            <input 
              type="password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-white/[0.08] border border-white/[0.12] rounded-2xl px-5 py-3.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#90dce1]/50 focus:border-[#90dce1]/30 transition-all duration-200"
              placeholder={t.passwordPlaceholder || t.password}
              required
            />
          </div>
          {error && (
            <div className="text-red-400 text-sm text-center py-2 px-4 bg-red-500/10 border border-red-500/20 rounded-xl">{error}</div>
          )}
          <button 
            type="submit"
            disabled={loading}
            className="w-full py-4 text-white font-semibold rounded-2xl transition-all duration-200 mt-6 shadow-lg shadow-[#90dce1]/20 disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-xl hover:shadow-[#90dce1]/30"
            style={{ background: loading ? 'rgba(144, 220, 225, 0.5)' : 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)' }}
          >
            {loading ? 'Logging in...' : t.loginBtn}
          </button>
        </form>
      </div>
    </div>
  );
};
