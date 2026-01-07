import React, { useState } from 'react';
import { changePassword } from '../api';
import { translations, Language } from '../translations';

interface ChangePasswordModalProps {
  isOpen: boolean;
  onClose: () => void;
  lang: Language;
}

export const ChangePasswordModal: React.FC<ChangePasswordModalProps> = ({ isOpen, onClose, lang }) => {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const t = translations[lang];

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess(false);

    // 验证
    if (!oldPassword || !newPassword || !confirmPassword) {
      setError(lang === 'zh' ? '请填写所有字段' : 'Please fill in all fields');
      return;
    }

    if (newPassword.length < 6) {
      setError(lang === 'zh' ? '新密码至少需要6个字符' : 'New password must be at least 6 characters');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError(lang === 'zh' ? '新密码和确认密码不匹配' : 'New password and confirm password do not match');
      return;
    }

    if (oldPassword === newPassword) {
      setError(lang === 'zh' ? '新密码不能与旧密码相同' : 'New password must be different from old password');
      return;
    }

    setLoading(true);
    try {
      await changePassword(oldPassword, newPassword);
      setSuccess(true);
      // 清空表单
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
      // 3秒后自动关闭
      setTimeout(() => {
        setSuccess(false);
        onClose();
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : (lang === 'zh' ? '修改密码失败' : 'Failed to change password'));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    if (!loading) {
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setError('');
      setSuccess(false);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[#1a1a1a] border border-white/[0.1] rounded-3xl p-8 w-full max-w-md mx-4 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-white">
            {lang === 'zh' ? '修改密码' : 'Change Password'}
          </h2>
          <button
            onClick={handleClose}
            disabled={loading}
            className="text-gray-400 hover:text-white transition-colors disabled:opacity-50"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        {success ? (
          <div className="text-center py-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green-500/20 flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-green-500">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </div>
            <p className="text-green-400 font-medium">
              {lang === 'zh' ? '密码修改成功！' : 'Password changed successfully!'}
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-3 text-red-400 text-sm">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {lang === 'zh' ? '当前密码' : 'Current Password'}
              </label>
              <input
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                className="w-full px-4 py-3 bg-white/[0.06] border border-white/[0.1] rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-[#90dce1]/50 focus:ring-2 focus:ring-[#90dce1]/20 transition-all"
                placeholder={lang === 'zh' ? '请输入当前密码' : 'Enter current password'}
                disabled={loading}
                autoFocus
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {lang === 'zh' ? '新密码' : 'New Password'}
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-4 py-3 bg-white/[0.06] border border-white/[0.1] rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-[#90dce1]/50 focus:ring-2 focus:ring-[#90dce1]/20 transition-all"
                placeholder={lang === 'zh' ? '请输入新密码（至少6个字符）' : 'Enter new password (min 6 characters)'}
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {lang === 'zh' ? '确认新密码' : 'Confirm New Password'}
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-4 py-3 bg-white/[0.06] border border-white/[0.1] rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-[#90dce1]/50 focus:ring-2 focus:ring-[#90dce1]/20 transition-all"
                placeholder={lang === 'zh' ? '请再次输入新密码' : 'Confirm new password'}
                disabled={loading}
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={handleClose}
                disabled={loading}
                className="flex-1 px-4 py-3 bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.1] rounded-xl text-white font-medium transition-all disabled:opacity-50"
              >
                {lang === 'zh' ? '取消' : 'Cancel'}
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 px-4 py-3 bg-gradient-to-r from-[#90dce1] to-[#6fc4cc] hover:from-[#7dd0d5] hover:to-[#5fb8c0] text-black font-medium rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (lang === 'zh' ? '修改中...' : 'Changing...') : (lang === 'zh' ? '确认修改' : 'Change Password')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

