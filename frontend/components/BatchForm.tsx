
import React, { useState, useRef, useEffect } from 'react';
import { Batch, VideoItem } from '../types';
import { translations, Language } from '../translations';

interface BatchFormProps {
  // Fixed: Changed from (batch: Batch) to (batch: any) because userId and userName are added in App.tsx
  onCreated: (batch: any) => void;
  lang: Language;
  userCredits: number;
}

export const BatchForm: React.FC<BatchFormProps> = ({ onCreated, lang, userCredits }) => {
  const t = translations[lang];
  const [images, setImages] = useState<File[]>([]);
  const [audio, setAudio] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  
  const imageInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const canAfford = userCredits >= images.length;

  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      const remainingSlots = 50 - images.length;
      const filesToAdd = selectedFiles.slice(0, remainingSlots);
      setImages(prev => [...prev, ...filesToAdd]);
    }
  };

  const removeImage = (index: number) => {
    setImages(prev => prev.filter((_, i) => i !== index));
  };

  const handleAudioChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setAudio(file);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(URL.createObjectURL(file));
      setIsPlaying(false);
    }
  };

  const togglePlayback = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (images.length === 0 || !audio || !canAfford) return;

    setIsGenerating(true);

    try {
      const { createBatch, getBatch } = await import('../api');
      
      // 提交批次
      const response = await createBatch(images, audio, prompt.trim() || "");
      
      // 获取批次详情
      const batch = await getBatch(response.batch_id);
      
      onCreated(batch);
      
      setImages([]);
      setAudio(null);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
      setPrompt('');
      setIsPlaying(false);
    } catch (error: any) {
      alert(error.message || 'Failed to create batch');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Image Upload Area */}
        <div className="space-y-3">
          <label className="text-sm font-medium text-gray-300">{t.imagesLabel}</label>
          <div 
            onClick={() => imageInputRef.current?.click()}
            className="border-2 border-dashed border-white/[0.12] rounded-3xl p-10 text-center cursor-pointer transition-all duration-200 bg-white/[0.04] backdrop-blur-sm group hover:border-[#90dce1]/40 hover:bg-white/[0.06]"
          >
            <div className="mx-auto w-14 h-14 rounded-2xl flex items-center justify-center mb-5 group-hover:scale-110 transition-transform" style={{ background: 'rgba(144, 220, 225, 0.12)' }}>
              <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#90dce1' }}><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
            </div>
            <p className="text-white font-medium text-base">{t.clickToUploadImages}</p>
            <p className="text-xs text-gray-400 mt-2">{t.itemsUploaded.replace('{count}', images.length.toString())}</p>
            <input 
              ref={imageInputRef}
              type="file" 
              multiple 
              accept="image/*" 
              className="hidden" 
              onChange={handleImageChange}
              disabled={images.length >= 50}
            />
          </div>
          
          {images.length > 0 && (
            <div className="grid grid-cols-5 gap-2.5 mt-5 max-h-52 overflow-y-auto p-2 bg-white/[0.03] backdrop-blur-sm rounded-2xl border border-white/[0.08]">
              {images.map((img, i) => (
                <div key={i} className="relative aspect-square group">
                  <img src={URL.createObjectURL(img)} className="w-full h-full object-cover rounded-xl border border-white/[0.1]" />
                  <button 
                    type="button"
                    onClick={() => removeImage(i)}
                    className="absolute -top-1.5 -right-1.5 bg-red-500 rounded-full p-1.5 opacity-0 group-hover:opacity-100 transition-all duration-200 shadow-lg"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Audio Upload Area */}
        <div className="space-y-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-300">{t.audioLabel}</label>
            <div 
              onClick={() => audioInputRef.current?.click()}
              className={`border-2 border-dashed rounded-3xl p-10 text-center cursor-pointer transition-all duration-200 bg-white/[0.04] backdrop-blur-sm relative group ${audio ? 'border-green-500/40' : 'border-white/[0.12] hover:border-[#90dce1]/40'} hover:bg-white/[0.06]`}
            >
              <div className={`mx-auto w-14 h-14 rounded-2xl flex items-center justify-center mb-5 transition-transform group-hover:scale-110 ${audio ? 'bg-green-500/15' : 'bg-[#90dce1]/12'}`}>
                {audio ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-green-400"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#90dce1' }}><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
                )}
              </div>
              <p className="text-white font-medium text-base truncate px-4">{audio ? audio.name : t.clickToUploadAudio}</p>
              <p className="text-xs text-gray-400 mt-2">{t.audioFormat}</p>
              
              {audio && audioUrl && (
                <div className="mt-5 flex flex-col items-center gap-3">
                  <audio 
                    ref={audioRef} 
                    src={audioUrl} 
                    onEnded={() => setIsPlaying(false)}
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={togglePlayback}
                    className="flex items-center gap-2.5 px-7 py-2.5 rounded-full border transition-all font-medium text-sm backdrop-blur-sm"
                    style={{ 
                      background: 'rgba(144, 220, 225, 0.15)',
                      borderColor: 'rgba(144, 220, 225, 0.3)',
                      color: '#90dce1'
                    }}
                  >
                    {isPlaying ? (
                      <>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
                        {t.pausePreview}
                      </>
                    ) : (
                      <>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        {t.playPreview}
                      </>
                    )}
                  </button>
                </div>
              )}

              <input 
                ref={audioInputRef}
                type="file" 
                accept="audio/*" 
                className="hidden" 
                onChange={handleAudioChange}
              />
            </div>
          </div>

          <div className="space-y-3">
            <label className="text-sm font-medium text-gray-300">{t.promptLabel}</label>
            <textarea 
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={t.promptPlaceholder}
              className="w-full bg-white/[0.04] backdrop-blur-sm border border-white/[0.12] rounded-3xl p-5 text-sm text-white placeholder-gray-500 focus:outline-none min-h-[140px] resize-none transition-all duration-200"
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
        </div>
      </div>

      <div className="pt-4 space-y-3">
        {images.length > 0 && (
          <div className="flex justify-between text-xs font-mono">
            <span className="text-gray-500">{t.costInfo.replace('{count}', images.length.toString())}</span>
            <span className={canAfford ? 'text-green-500' : 'text-red-500'}>
              {canAfford ? '✔' : t.insufficientCredits}
            </span>
          </div>
        )}
        <button
          type="submit"
          disabled={isGenerating || images.length === 0 || !audio || !canAfford}
          className="w-full py-6 text-white font-semibold text-lg rounded-3xl transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-3 shadow-xl hover:shadow-2xl"
          style={{ 
            background: (isGenerating || images.length === 0 || !audio || !canAfford)
              ? 'rgba(144, 220, 225, 0.3)'
              : 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
            boxShadow: '0 10px 40px rgba(144, 220, 225, 0.25)'
          }}
        >
          {isGenerating ? (
            <>
              <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              {t.generating}
            </>
          ) : (
            <>
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              {t.generateBtn.replace('{count}', images.length.toString())}
            </>
          )}
        </button>
      </div>
    </form>
  );
};
