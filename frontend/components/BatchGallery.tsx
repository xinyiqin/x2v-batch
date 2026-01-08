
import React, { useState, useEffect } from 'react';
import { Batch, VideoItem } from '../types';
import { translations, Language } from '../translations';
import { getBatch, getFileUrl } from '../api';

interface BatchGalleryProps {
  batch: Batch;
  lang: Language;
}

export const BatchGallery: React.FC<BatchGalleryProps> = ({ batch, lang }) => {
  const t = translations[lang];
  const [selectedItem, setSelectedItem] = useState<VideoItem | null>(null);
  const [currentBatch, setCurrentBatch] = useState<Batch>(batch);
  const [isExporting, setIsExporting] = useState(false);
  const [videoLoadError, setVideoLoadError] = useState<string | null>(null);

  // 当 batch prop 改变时，更新 currentBatch
  useEffect(() => {
    setCurrentBatch(batch);
  }, [batch.id, batch]);

  // 下载单个视频
  const handleDownloadVideo = async (videoUrl: string, itemId: string): Promise<void> => {
    if (!videoUrl) {
      throw new Error(t.videoNotReady || '视频尚未生成完成');
    }

    return new Promise((resolve) => {
      // 使用直接下载链接（最简单可靠的方法，支持跨域）
      const link = document.createElement('a');
      link.href = videoUrl;
      link.download = `video_${itemId}_${Date.now()}.mp4`;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      
      // 添加点击事件监听
      const handleClick = () => {
        // 给浏览器一些时间处理下载
        setTimeout(() => {
          resolve();
        }, 300);
      };
      
      link.addEventListener('click', handleClick, { once: true });
      
      // 尝试触发下载
      document.body.appendChild(link);
      link.click();
      
      // 延迟移除，确保点击事件被触发
      setTimeout(() => {
        document.body.removeChild(link);
        // 如果点击事件没有触发，也 resolve（浏览器可能阻止了下载，但会打开新标签页）
        resolve();
      }, 200);
    });
  };

  // 导出全部已完成的视频为zip文件
  const handleExportAll = async () => {
    const completedItems = currentBatch.items.filter(
      item => item.status === 'completed' && item.videoUrl && item.videoUrl.trim()
    );

    if (completedItems.length === 0) {
      alert(lang === 'zh' ? '没有已完成的视频可以导出' : 'No completed videos to export');
      return;
    }

    setIsExporting(true);

    try {
      const { exportBatchVideos } = await import('../api');
      
      // 调用后端API获取zip文件
      const zipBlob = await exportBatchVideos(currentBatch.id);
      
      // 创建下载链接
      const url = window.URL.createObjectURL(zipBlob);
      const link = document.createElement('a');
      link.href = url;
      
      // 生成文件名
      const batchNameSafe = currentBatch.name.replace(/[^a-zA-Z0-9-_ ]/g, '').trim();
      const timestamp = new Date().toISOString().slice(0, 10);
      link.download = `${batchNameSafe}_${timestamp}.zip`;
      
      // 触发下载
      document.body.appendChild(link);
      link.click();
      
      // 清理
      setTimeout(() => {
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        setIsExporting(false);
      }, 100);
      
    } catch (error: any) {
      console.error('Export failed:', error);
      const errorMsg = error?.message || (lang === 'zh' ? '导出过程中出现错误' : 'Export failed');
      alert(errorMsg);
      setIsExporting(false);
    }
  };

  // 当选择新项目时，重置视频加载错误
  useEffect(() => {
    setVideoLoadError(null);
  }, [selectedItem?.id]);

  // 轮询更新批次状态
  useEffect(() => {
    const hasProcessing = currentBatch.items.some(
      item => item.status === 'pending' || item.status === 'processing'
    );

    if (hasProcessing) {
      const interval = setInterval(async () => {
        try {
          const updatedBatch = await getBatch(batch.id);
          setCurrentBatch(updatedBatch);
          
          // 如果所有任务都完成了，停止轮询
          const stillProcessing = updatedBatch.items.some(
            item => item.status === 'pending' || item.status === 'processing'
          );
          if (!stillProcessing) {
            clearInterval(interval);
          }
        } catch (error) {
          console.error('Failed to refresh batch:', error);
        }
      }, 5000); // 每5秒刷新一次

      return () => clearInterval(interval);
    }
  }, [batch.id, currentBatch.items]);

  return (
    <div className="space-y-4 md:space-y-8">
      {/* Batch Header Info */}
      <div className="bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-2xl md:rounded-3xl p-4 md:p-8 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 md:gap-6 shadow-xl">
        <div className="flex-1 w-full">
          <h2 className="text-xl md:text-3xl font-semibold text-white mb-3 md:mb-4 tracking-tight">{currentBatch.name}</h2>
          <div className="flex flex-wrap items-center gap-2 md:gap-3 mb-3 md:mb-4 text-xs md:text-sm">
            <span className="flex items-center gap-2 bg-white/[0.08] px-3 py-1.5 rounded-full text-gray-300 border border-white/[0.1]">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
              {currentBatch.audioName}
            </span>
            <span className="flex items-center gap-2 bg-white/[0.08] px-3 py-1.5 rounded-full text-gray-300 border border-white/[0.1]">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
              {t.videosCount.replace('{count}', currentBatch.imageCount.toString())}
            </span>
            <span className="text-xs text-gray-500">{t.created}: {new Date(currentBatch.timestamp).toLocaleString()}</span>
          </div>
          
          {/* 进度条 */}
          {currentBatch.progress && (
            <div className="mt-6 space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-300 font-medium">{t.overallProgress || '总体进度'}</span>
                <span className="font-semibold" style={{ color: '#90dce1' }}>{currentBatch.progress.overall_progress}%</span>
              </div>
              <div className="relative w-full h-2.5 bg-white/[0.08] rounded-full overflow-hidden">
                <div 
                  className="absolute top-0 left-0 h-full rounded-full transition-all duration-500 ease-out"
                  style={{ 
                    width: `${currentBatch.progress.overall_progress}%`,
                    background: 'linear-gradient(90deg, #90dce1 0%, #6fc4cc 100%)'
                  }}
                />
              </div>
              <div className="flex flex-wrap items-center gap-3 md:gap-5 text-xs text-gray-400">
                <span>✅ {currentBatch.progress.completed} {t.completed || '已完成'}</span>
                <span>⏳ {currentBatch.progress.processing} {t.processing || '处理中'}</span>
                <span>⏸️ {currentBatch.progress.pending} {t.pending || '等待中'}</span>
                {currentBatch.progress.failed > 0 && (
                  <span className="text-red-400">❌ {currentBatch.progress.failed} {t.failed || '失败'}</span>
                )}
              </div>
            </div>
          )}
          
          {currentBatch.prompt && (
            <p className="mt-6 text-gray-300 text-sm border-l-3 pl-5 py-3 rounded-r-xl" style={{ borderColor: '#90dce1', background: 'rgba(144, 220, 225, 0.05)' }}>
              &ldquo;{currentBatch.prompt}&rdquo;
            </p>
          )}
        </div>
        <button 
          onClick={handleExportAll}
          disabled={isExporting || currentBatch.items.filter(item => item.status === 'completed' && item.videoUrl).length === 0}
          className="w-full md:w-auto flex items-center justify-center gap-2.5 text-white px-5 md:px-7 py-3 md:py-3.5 rounded-xl md:rounded-2xl font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
          style={{ 
            background: (isExporting || currentBatch.items.filter(item => item.status === 'completed' && item.videoUrl).length === 0) 
              ? 'rgba(144, 220, 225, 0.3)' 
              : 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
            boxShadow: '0 10px 30px rgba(144, 220, 225, 0.2)'
          }}
        >
          {isExporting ? (
            <>
              <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              {t.exporting || '导出中...'}
            </>
          ) : (
            <>
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
          {t.exportAll}
            </>
          )}
        </button>
      </div>

      {/* Waterfall / Grid Display */}
      <div className="columns-1 sm:columns-2 md:columns-3 lg:columns-4 gap-3 md:gap-4 space-y-3 md:space-y-4">
        {currentBatch.items.map((item) => (
          <div 
            key={item.id} 
            className="break-inside-avoid relative group cursor-pointer overflow-hidden rounded-3xl bg-white/[0.04] backdrop-blur-xl border border-white/[0.08] hover:border-[#90dce1]/40 transition-all duration-300 hover:shadow-2xl mb-4"
            style={{ boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3)' }}
            onClick={() => setSelectedItem(item)}
          >
            {/* Source preview overlay */}
            {item.sourceImage && (
              <div className="absolute top-2 left-2 z-30 w-8 h-8 rounded-lg border border-white/20 overflow-hidden shadow-lg opacity-80 group-hover:opacity-100 transition-opacity bg-black/20 pointer-events-none">
                 <img 
                   src={getFileUrl(item.sourceImage, 'images')} 
                   className="w-full h-full object-cover"
                   alt="Source image"
                   onError={(e) => {
                     // 如果图片加载失败，尝试使用完整 URL
                     const target = e.target as HTMLImageElement;
                     if (!target.src.includes('api/files')) {
                       target.src = getFileUrl(item.sourceImage, 'images');
                     }
                   }}
                 />
            </div>
            )}

            {/* Main result image (video preview or placeholder) */}
            {item.status === 'completed' && item.videoUrl && item.videoUrl.trim() ? (
              <div className="relative w-full aspect-[9/16] bg-black overflow-hidden">
                {/* 使用源图片作为预览图 */}
                {item.sourceImage ? (
                  <img 
                    src={getFileUrl(item.sourceImage, 'images')} 
                    alt={`Video Preview ${item.id}`}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105 relative z-0" 
                    loading="eager"
                    decoding="async"
                    style={{ 
                      display: 'block',
                      opacity: 1,
                      visibility: 'visible',
                      minHeight: '100%',
                      minWidth: '100%',
                      position: 'relative',
                      zIndex: 0
                    }}
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      console.error('Image load error for item:', item.id, 'sourceImage:', item.sourceImage, 'Current src:', target.src);
                      // 如果当前 URL 不包含 api/files，尝试重新构建
                      if (!target.src.includes('api/files')) {
                        const newUrl = getFileUrl(item.sourceImage, 'images');
                        if (newUrl !== target.src) {
                          target.src = newUrl;
                        }
                      }
                    }}
                    onLoad={(e) => {
                      // 确保图片显示
                      const target = e.target as HTMLImageElement;
                      target.style.opacity = '1';
                      target.style.visibility = 'visible';
                      target.style.display = 'block';
                      target.style.zIndex = '0';
                    }}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[#90dce1]/10 to-[#6fc4cc]/10">
                    <p className="text-gray-400 text-sm">无预览图</p>
                  </div>
                )}
                {/* 视频播放指示器 - 只在 hover 时显示 */}
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-black/30 backdrop-blur-[2px] pointer-events-none z-10">
                  <div className="w-20 h-20 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center text-white border-2 border-white/40 shadow-xl">
                    <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="currentColor">
                      <polygon points="5 3 19 12 5 21 5 3"/>
                    </svg>
                  </div>
                </div>
              </div>
            ) : (
              <div className="w-full aspect-[9/16] flex flex-col items-center justify-center p-4" style={{ background: 'linear-gradient(135deg, rgba(144, 220, 225, 0.1) 0%, rgba(111, 196, 204, 0.1) 100%)' }}>
                {item.status === 'processing' ? (
                  <div className="text-center w-full">
                    {/* 进度条 */}
                    {item.progress !== undefined && (
                      <div className="mb-4 w-full px-4">
                        <div className="relative w-full h-2 bg-white/[0.12] rounded-full overflow-hidden mb-2.5">
                          <div 
                            className="absolute top-0 left-0 h-full rounded-full transition-all duration-500 ease-out"
                            style={{ 
                              width: `${item.progress}%`,
                              background: 'linear-gradient(90deg, #90dce1 0%, #6fc4cc 100%)'
                            }}
                          />
                        </div>
                        <p className="text-sm font-semibold" style={{ color: '#90dce1' }}>{item.progress}%</p>
                      </div>
                    )}
                    <svg className="animate-spin h-7 w-7 mx-auto mb-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style={{ color: '#90dce1' }}>
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <p className="text-sm font-medium" style={{ color: '#90dce1' }}>{t.processing || 'Processing...'}</p>
                  </div>
                ) : item.status === 'failed' ? (
                  <div className="text-center text-red-400">
                    <p className="text-xs font-semibold">❌ {t.failed || 'Failed'}</p>
                    {item.error_msg && <p className="text-[10px] mt-1 text-red-300">{item.error_msg}</p>}
                  </div>
                ) : (
                  <div className="text-center text-gray-400">
                    <p className="text-xs">⏸️ {t.pending || 'Pending'}</p>
                  </div>
                )}
            </div>
            )}

            {/* Label */}
            <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/90 via-black/70 to-transparent z-20 pointer-events-none">
               <p className="text-[10px] font-mono" style={{ color: '#90dce1' }}>ID: {item.id.split('-').pop()}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Video Modal */}
      {selectedItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-300">
          <div className="relative max-w-lg w-full bg-white/[0.05] backdrop-blur-2xl rounded-3xl overflow-hidden shadow-2xl border border-white/[0.1]">
            <button 
              onClick={() => setSelectedItem(null)}
              className="absolute top-5 right-5 z-10 p-2.5 bg-white/[0.1] hover:bg-white/[0.15] rounded-full text-white transition-all duration-200 backdrop-blur-sm"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
            
            <div className="aspect-[9/16] w-full bg-black relative">
              {selectedItem.videoUrl && selectedItem.videoUrl.trim() && selectedItem.status === 'completed' && !videoLoadError ? (
                <video 
                  src={selectedItem.videoUrl} 
                  controls 
                  className="w-full h-full object-contain"
                  autoPlay
                  onError={(e) => {
                    console.error('Video load error:', selectedItem.videoUrl);
                    setVideoLoadError('视频加载失败');
                  }}
                  onLoadStart={() => {
                    setVideoLoadError(null);
                  }}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <div className="p-8 backdrop-blur-xl border rounded-2xl text-center max-w-[80%]" style={{ 
                    background: videoLoadError ? 'rgba(255, 59, 48, 0.1)' : 'rgba(144, 220, 225, 0.1)', 
                    borderColor: videoLoadError ? 'rgba(255, 59, 48, 0.3)' : 'rgba(144, 220, 225, 0.3)' 
                  }}>
                    {videoLoadError ? (
                      <>
                        <p className="text-white font-semibold mb-2 text-red-400">视频加载失败</p>
                        <p className="text-sm text-red-300">无法加载视频，请检查网络连接或稍后重试</p>
                        <p className="text-xs text-gray-400 mt-2 break-all">{selectedItem.videoUrl}</p>
                      </>
                    ) : selectedItem.status === 'completed' && (!selectedItem.videoUrl || !selectedItem.videoUrl.trim()) ? (
                      <>
                        <p className="text-white font-semibold mb-2">视频尚未生成</p>
                        <p className="text-sm" style={{ color: '#90dce1' }}>视频生成完成但 URL 不可用</p>
                      </>
                    ) : selectedItem.status === 'processing' ? (
                      <>
                        <p className="text-white font-semibold mb-2">视频生成中</p>
                        <p className="text-sm" style={{ color: '#90dce1' }}>请稍候，视频正在生成...</p>
                      </>
                    ) : selectedItem.status === 'failed' ? (
                      <>
                        <p className="text-white font-semibold mb-2 text-red-400">生成失败</p>
                        <p className="text-sm text-red-300">{selectedItem.error_msg || '视频生成失败'}</p>
                      </>
                    ) : (
                      <>
                        <p className="text-white font-semibold mb-2">等待处理</p>
                        <p className="text-sm" style={{ color: '#90dce1' }}>视频尚未开始生成</p>
                      </>
                    )}
                 </div>
               </div>
              )}
            </div>

            <div className="p-6 bg-black/20 backdrop-blur-xl">
               <div className="flex justify-between items-center">
                 <div>
                   <h3 className="text-white font-semibold">{t.videoPreview}</h3>
                   <p className="text-xs text-gray-400 mt-1">Item ID: {selectedItem.id}</p>
                 </div>
                 <div className="flex gap-3">
                   <button className="p-3 bg-white/[0.08] hover:bg-white/[0.12] rounded-xl transition-all duration-200 border border-white/[0.1]">
                     <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                   </button>
                   <button 
                     onClick={() => selectedItem && selectedItem.videoUrl && handleDownloadVideo(selectedItem.videoUrl, selectedItem.id)}
                     disabled={!selectedItem || !selectedItem.videoUrl || selectedItem.status !== 'completed'}
                     className="px-6 py-2.5 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
                     style={{ 
                       background: (!selectedItem || !selectedItem.videoUrl || selectedItem.status !== 'completed')
                         ? 'rgba(144, 220, 225, 0.3)'
                         : 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
                       boxShadow: '0 8px 20px rgba(144, 220, 225, 0.2)'
                     }}
                   >
                     {t.downloadMp4}
                   </button>
                 </div>
               </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
