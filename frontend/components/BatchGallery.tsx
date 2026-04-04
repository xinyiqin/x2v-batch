
import React, { useState, useEffect } from 'react';
import { Batch, VideoItem } from '../types';
import { translations, Language } from '../translations';
import {
  getBatch,
  getFileUrl,
  cancelBatchItem,
  resumeBatchItem,
  retryFailedBatchItems,
  isProxyMediaPath,
  fetchResolvedUrl,
  getItemInputImageApiPath,
  getItemResultVideoApiPath,
} from '../api';

interface BatchGalleryProps {
  batch: Batch;
  lang: Language;
  /** 提交时的前端图片缓存 (batchId -> blob URLs)，优先作缩略图；完成的任务才走 input_url */
  batchImageCache?: Record<string, string[]>;
}

/** 当 sourceImage 为 input_url 代理路径时，先 fetch 取真实 URL 再渲染 img */
function ResolvedImage({
  batchId,
  itemId,
  sourceImage,
  className,
  alt,
  onError,
  onLoad,
}: {
  batchId: string;
  itemId: string;
  sourceImage: string;
  className?: string;
  alt?: string;
  onError?: (e: React.SyntheticEvent<HTMLImageElement>) => void;
  onLoad?: (e: React.SyntheticEvent<HTMLImageElement>) => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    if (!isProxyMediaPath(sourceImage)) return;
    setErr(false);
    fetchResolvedUrl(getItemInputImageApiPath(batchId, itemId))
      .then(setSrc)
      .catch(() => setErr(true));
  }, [batchId, itemId, sourceImage]);
  if (err || !src) return null;
  return <img src={src} className={className} alt={alt || ''} onError={onError} onLoad={onLoad} />;
}

export const BatchGallery: React.FC<BatchGalleryProps> = ({ batch, lang, batchImageCache }) => {
  const t = translations[lang];
  const [selectedItem, setSelectedItem] = useState<VideoItem | null>(null);
  const [currentBatch, setCurrentBatch] = useState<Batch>(batch);
  const [isExporting, setIsExporting] = useState(false);
  const [actionItemIds, setActionItemIds] = useState<string[]>([]);
  const [isRetryingBatch, setIsRetryingBatch] = useState(false);
  const [videoLoadError, setVideoLoadError] = useState<string | null>(null);
  /** 详情弹窗中已完成的 item 通过 result_url 接口取到的视频 URL */
  const [resolvedVideoUrl, setResolvedVideoUrl] = useState<string | null>(null);
  /** 单视频下载中（fetch 成 blob 再触发下载，兼容移动端） */
  const [downloadVideoLoading, setDownloadVideoLoading] = useState(false);

  // 当 batch prop 改变时，更新 currentBatch
  useEffect(() => {
    setCurrentBatch(batch);
  }, [batch.id, batch]);

  // 参考 lightx2v 前端：先 fetch 成 blob，再用 blob URL 触发下载（移动端对同源 blob 更友好）
  const handleDownloadVideo = async (videoUrl: string, itemId: string) => {
    if (!videoUrl) {
      alert(t.videoNotReady || '视频尚未生成完成');
      return;
    }
    setDownloadVideoLoading(true);
    try {
      const response = await fetch(videoUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const filename = `video_${itemId}_${Date.now()}.mp4`;
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    } catch (e) {
      console.error('Download video failed:', e);
      // 跨域时 fetch 会失败，移动端退化为新开页打开，用户可长按保存
      try {
        window.open(videoUrl, '_blank', 'noopener,noreferrer');
      } catch {
        alert(lang === 'zh' ? '下载失败，请重试或在新标签页打开链接' : 'Download failed, please retry or open link in new tab');
      }
    } finally {
      setDownloadVideoLoading(false);
    }
  };

  // 批量下载所有已完成的视频（前端直接下载，不经过后端打包；URL 由 export 接口按 result_url 返回）
  const handleExportAll = async () => {
    const completedItems = currentBatch.items.filter(
      item => item.status === 'completed' && (item.videoUrl?.trim() || item.api_task_id)
    );

    if (completedItems.length === 0) {
      alert(lang === 'zh' ? '没有已完成的视频可以下载' : 'No completed videos to download');
      return;
    }

    setIsExporting(true);

    try {
      const { getBatchExportList, batchDownloadFiles } = await import('../api');
      
      // 获取下载清单
      const exportList = await getBatchExportList(currentBatch.id);
      
      if (!exportList.files || exportList.files.length === 0) {
        throw new Error(lang === 'zh' ? '没有可下载的文件' : 'No files to download');
      }
      
      // 批量下载文件（带进度提示）
      let currentCount = 0;
      const total = exportList.files.length;
      
      // 显示进度提示
      const progressMsg = lang === 'zh' 
        ? `正在下载 ${currentCount} / ${total} 个视频…`
        : `Downloading ${currentCount} / ${total} videos…`;
      
      await batchDownloadFiles(exportList.files, (current, total) => {
        currentCount = current;
        // 更新进度提示（可选，如果需要实时显示）
        if (current % 5 === 0 || current === total) {
          console.log(`${progressMsg.replace(/\d+/, current.toString())}`);
        }
      });
      
      // 下载完成提示
      alert(lang === 'zh' 
        ? `已开始下载 ${exportList.total} 个视频，请在浏览器下载列表查看`
        : `Started downloading ${exportList.total} videos, please check your browser's download list`
      );
      
      setIsExporting(false);
      
    } catch (error: any) {
      console.error('Batch download failed:', error);
      const errorMsg = error?.message || (lang === 'zh' ? '批量下载过程中出现错误' : 'Batch download failed');
      alert(errorMsg);
      setIsExporting(false);
    }
  };

  // 当选中已完成项时，通过 result_url 接口取视频 URL
  useEffect(() => {
    if (!selectedItem || selectedItem.status !== 'completed' || !selectedItem.api_task_id) {
      setResolvedVideoUrl(null);
      return;
    }
    setResolvedVideoUrl(null);
    setVideoLoadError(null);
    fetchResolvedUrl(getItemResultVideoApiPath(currentBatch.id, selectedItem.id))
      .then(setResolvedVideoUrl)
      .catch(() => setVideoLoadError('无法获取视频地址'));
  }, [selectedItem?.id, selectedItem?.status, selectedItem?.api_task_id, currentBatch.id]);

  // 当选择新项目时，重置视频加载错误
  useEffect(() => {
    setVideoLoadError(null);
  }, [selectedItem?.id]);

  const updateActioning = (itemId: string, isActioning: boolean) => {
    setActionItemIds((prev) => {
      if (isActioning) {
        return prev.includes(itemId) ? prev : [...prev, itemId];
      }
      return prev.filter((id) => id !== itemId);
    });
  };

  const refreshBatch = async () => {
    const updatedBatch = await getBatch(currentBatch.id);
    setCurrentBatch(updatedBatch);
    if (selectedItem) {
      const updatedItem = updatedBatch.items.find(item => item.id === selectedItem.id);
      if (updatedItem) {
        setSelectedItem(updatedItem);
      }
    }
  };

  const handleCancelItem = async (itemId: string) => {
    try {
      updateActioning(itemId, true);
      await cancelBatchItem(currentBatch.id, itemId);
      await refreshBatch();
    } catch (error: any) {
      console.error('Cancel item failed:', error);
      alert(error?.message || (lang === 'zh' ? '取消失败' : 'Cancel failed'));
    } finally {
      updateActioning(itemId, false);
    }
  };

  const handleRetryItem = async (itemId: string) => {
    try {
      updateActioning(itemId, true);
      await resumeBatchItem(currentBatch.id, itemId);
      await refreshBatch();
    } catch (error: any) {
      console.error('Retry item failed:', error);
      alert(error?.message || (lang === 'zh' ? '重试失败' : 'Retry failed'));
    } finally {
      updateActioning(itemId, false);
    }
  };

  const handleRetryFailedItems = async () => {
    try {
      setIsRetryingBatch(true);
      await retryFailedBatchItems(currentBatch.id);
      await refreshBatch();
    } catch (error: any) {
      console.error('Retry failed items failed:', error);
      alert(error?.message || (lang === 'zh' ? '批量重试失败' : 'Batch retry failed'));
    } finally {
      setIsRetryingBatch(false);
    }
  };

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

  const isBatchComplete = currentBatch.items.every(
    item => item.status === 'completed' || item.status === 'failed' || item.status === 'cancelled'
  );

  const hasFailedItems = currentBatch.items.some(item => item.status === 'failed');
  const hasCancelledItems = currentBatch.items.some(item => item.status === 'cancelled');
  const hasRetryableItems = hasFailedItems || hasCancelledItems;
  const isSelectedActioning = selectedItem ? actionItemIds.includes(selectedItem.id) : false;

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
            {isBatchComplete && currentBatch.creditsUsed !== undefined && currentBatch.creditsUsed > 0 && (
              <span className="flex items-center gap-2 bg-white/[0.08] px-3 py-1.5 rounded-full text-gray-300 border border-white/[0.1]">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                {currentBatch.creditsUsed} {t.credits}
              </span>
            )}
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
                {(currentBatch.progress.queued ?? 0) > 0 && (
                  <span>📋 {currentBatch.progress.queued} {t.queued || '排队中'}</span>
                )}
                <span>⏸️ {currentBatch.progress.pending} {t.pending || '等待中'}</span>
                {currentBatch.progress.failed > 0 && (
                  <span className="text-red-400">❌ {currentBatch.progress.failed} {t.failed || '失败'}</span>
                )}
                {(currentBatch.progress.cancelled ?? 0) > 0 && (
                  <span className="text-gray-400">🚫 {currentBatch.progress.cancelled} {t.cancelled || '已取消'}</span>
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
        <div className="w-full md:w-auto flex flex-col md:flex-row gap-3">
          <button
            onClick={handleRetryFailedItems}
            disabled={isRetryingBatch || !hasRetryableItems}
            className="w-full md:w-auto flex items-center justify-center gap-2.5 text-white px-5 md:px-7 py-3 md:py-3.5 rounded-xl md:rounded-2xl font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
            style={{
              background: (isRetryingBatch || !hasRetryableItems)
                ? 'rgba(255, 159, 10, 0.3)'
                : 'linear-gradient(135deg, #ffb84d 0%, #ff8c1a 100%)',
              boxShadow: '0 10px 30px rgba(255, 159, 10, 0.2)',
            }}
          >
            {isRetryingBatch ? (
              <>
                <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                {t.retrying || '重试中...'}
              </>
            ) : (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 3 3 9 9 9"/></svg>
                {t.retryFailed || '重试失败任务'}
              </>
            )}
          </button>
          <button
            onClick={handleExportAll}
            disabled={isExporting || currentBatch.items.filter(item => item.status === 'completed' && (item.videoUrl || item.api_task_id)).length === 0}
            className="w-full md:w-auto flex items-center justify-center gap-2.5 text-white px-5 md:px-7 py-3 md:py-3.5 rounded-xl md:rounded-2xl font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
            style={{
              background: (isExporting || currentBatch.items.filter(item => item.status === 'completed' && (item.videoUrl || item.api_task_id)).length === 0)
                ? 'rgba(144, 220, 225, 0.3)'
                : 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
              boxShadow: '0 10px 30px rgba(144, 220, 225, 0.2)',
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
      </div>

      {/* Grid Display - 使用 Grid 替代 columns，Safari 下 columns 布局易出现内容不铺满、不滚动 */}
      <div className="w-full grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-4">
        {currentBatch.items.map((item, index) => {
          const isActioning = actionItemIds.includes(item.id);
          const cachedThumb = batchImageCache?.[currentBatch.id]?.[index];
          return (
          <div
            key={item.id}
            className="relative group cursor-pointer overflow-hidden rounded-3xl bg-white/[0.04] backdrop-blur-xl border border-white/[0.08] hover:border-[#90dce1]/40 transition-all duration-300 hover:shadow-2xl"
            style={{ boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3)' }}
            onClick={() => setSelectedItem(item)}
          >
            {/* 缩略图：优先前端缓存，完成的任务才走 input_url */}
            {(cachedThumb || item.sourceImage) && (
              <div className="absolute top-2 left-2 z-30 w-8 h-8 rounded-lg border border-white/20 overflow-hidden shadow-lg opacity-80 group-hover:opacity-100 transition-opacity bg-black/20 pointer-events-none">
                {cachedThumb ? (
                  <img src={cachedThumb} className="w-full h-full object-cover" alt="Source image" />
                ) : item.status === 'completed' && item.api_task_id && isProxyMediaPath(item.sourceImage) ? (
                  <ResolvedImage
                    batchId={currentBatch.id}
                    itemId={item.id}
                    sourceImage={item.sourceImage}
                    className="w-full h-full object-cover"
                    alt="Source image"
                  />
                ) : item.sourceImage && !isProxyMediaPath(item.sourceImage) ? (
                  <img
                    src={getFileUrl(item.sourceImage, 'images')}
                    className="w-full h-full object-cover"
                    alt="Source image"
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      if (!target.src.includes('api/files')) {
                        target.src = getFileUrl(item.sourceImage, 'images');
                      }
                    }}
                  />
                ) : null}
              </div>
            )}

            {/* Main result image (video preview or placeholder) */}
            {item.status === 'completed' && (item.videoUrl?.trim() || item.api_task_id) ? (
              <div className="relative w-full aspect-[9/16] bg-black overflow-hidden">
                {cachedThumb ? (
                  <img
                    src={cachedThumb}
                    alt={`Video Preview ${item.id}`}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105 relative z-0"
                    loading="eager"
                    decoding="async"
                  />
                ) : item.sourceImage && isProxyMediaPath(item.sourceImage) ? (
                  <ResolvedImage
                    batchId={currentBatch.id}
                    itemId={item.id}
                    sourceImage={item.sourceImage}
                    alt={`Video Preview ${item.id}`}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105 relative z-0"
                  />
                ) : item.sourceImage ? (
                  <img
                    src={getFileUrl(item.sourceImage, 'images')}
                    alt={`Video Preview ${item.id}`}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105 relative z-0"
                    loading="eager"
                    decoding="async"
                    style={{ display: 'block', opacity: 1, visibility: 'visible', minHeight: '100%', minWidth: '100%', position: 'relative', zIndex: 0 }}
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      if (!target.src.includes('api/files')) {
                        target.src = getFileUrl(item.sourceImage, 'images');
                      }
                    }}
                    onLoad={(e) => {
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
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCancelItem(item.id);
                      }}
                      disabled={isActioning}
                      className="mt-3 px-3 py-1.5 text-xs font-medium rounded-lg text-white bg-white/10 hover:bg-white/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {t.cancel || '取消'}
                    </button>
                  </div>
                ) : item.status === 'failed' ? (
                  <div className="text-center text-red-400">
                    <p className="text-xs font-semibold">❌ {t.failed || 'Failed'}</p>
                    {item.error_msg && <p className="text-[10px] mt-1 text-red-300">{item.error_msg}</p>}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRetryItem(item.id);
                      }}
                      disabled={isActioning}
                      className="mt-3 px-3 py-1.5 text-xs font-medium rounded-lg text-white bg-amber-500/80 hover:bg-amber-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {t.retry || '重试'}
                    </button>
                  </div>
                ) : item.status === 'cancelled' ? (
                  <div className="text-center text-gray-400">
                    <p className="text-xs">🚫 {t.cancelled || 'Cancelled'}</p>
                  </div>
                ) : item.status === 'pending' && !item.api_task_id ? (
                  <div className="text-center text-gray-400">
                    <p className="text-xs">📋 {t.queued || '排队中'}</p>
                  </div>
                ) : (
                  <div className="text-center text-gray-400">
                    <p className="text-xs">⏸️ {t.pending || 'Pending'}</p>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCancelItem(item.id);
                      }}
                      disabled={isActioning}
                      className="mt-3 px-3 py-1.5 text-xs font-medium rounded-lg text-white bg-white/10 hover:bg-white/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {t.cancel || '取消'}
                    </button>
                  </div>
                )}
            </div>
            )}

            {/* Label */}
            <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/90 via-black/70 to-transparent z-20 pointer-events-none">
               <p className="text-[10px] font-mono" style={{ color: '#90dce1' }}>ID: {item.id.split('-').pop()}</p>
            </div>
          </div>
        );
        })}
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
              {resolvedVideoUrl && selectedItem.status === 'completed' && !videoLoadError ? (
                <video
                  src={resolvedVideoUrl}
                  controls
                  className="w-full h-full object-contain"
                  autoPlay
                  onError={() => setVideoLoadError('视频加载失败')}
                  onLoadStart={() => setVideoLoadError(null)}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <div className="p-8 backdrop-blur-xl border rounded-2xl text-center max-w-[80%]" style={{
                    background: videoLoadError ? 'rgba(255, 59, 48, 0.1)' : 'rgba(144, 220, 225, 0.1)',
                    borderColor: videoLoadError ? 'rgba(255, 59, 48, 0.3)' : 'rgba(144, 220, 225, 0.3)',
                  }}>
                    {videoLoadError ? (
                      <>
                        <p className="text-white font-semibold mb-2 text-red-400">视频加载失败</p>
                        <p className="text-sm text-red-300">无法加载视频，请检查网络连接或稍后重试</p>
                      </>
                    ) : selectedItem.status === 'completed' && !resolvedVideoUrl ? (
                      <>
                        <p className="text-white font-semibold mb-2">视频尚未生成</p>
                        <p className="text-sm" style={{ color: '#90dce1' }}>正在获取视频地址…</p>
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
                    ) : selectedItem.status === 'cancelled' ? (
                      <>
                        <p className="text-white font-semibold mb-2 text-gray-400">任务已取消</p>
                        <p className="text-sm" style={{ color: '#90dce1' }}>已停止生成，不会扣除积分</p>
                      </>
                    ) : selectedItem.status === 'pending' && !selectedItem.api_task_id ? (
                      <>
                        <p className="text-white font-semibold mb-2">排队中</p>
                        <p className="text-sm" style={{ color: '#90dce1' }}>正在提交到服务器，请稍候</p>
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
                  {selectedItem.status === 'failed' && (
                    <button
                      onClick={() => handleRetryItem(selectedItem.id)}
                      disabled={isSelectedActioning}
                      className="px-4 py-2.5 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
                      style={{
                        background: isSelectedActioning
                          ? 'rgba(255, 159, 10, 0.3)'
                          : 'linear-gradient(135deg, #ffb84d 0%, #ff8c1a 100%)',
                        boxShadow: '0 8px 20px rgba(255, 159, 10, 0.2)',
                      }}
                    >
                      {t.retry || '重试'}
                    </button>
                  )}
                  {((selectedItem.status === 'pending' && selectedItem.api_task_id) || selectedItem.status === 'processing') && (
                    <button
                      onClick={() => handleCancelItem(selectedItem.id)}
                      disabled={isSelectedActioning}
                      className="px-4 py-2.5 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg hover:shadow-xl bg-white/10 hover:bg-white/20"
                    >
                      {t.cancel || '取消'}
                    </button>
                  )}
                   <button
                     type="button"
                     onClick={() => selectedItem && resolvedVideoUrl && selectedItem.status === 'completed' && handleDownloadVideo(resolvedVideoUrl, selectedItem.id)}
                     disabled={!selectedItem || !resolvedVideoUrl || selectedItem.status !== 'completed' || downloadVideoLoading}
                     className="px-6 py-2.5 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg hover:shadow-xl inline-flex items-center justify-center gap-2"
                     style={{
                       background: (!selectedItem || !resolvedVideoUrl || selectedItem.status !== 'completed' || downloadVideoLoading)
                         ? 'rgba(144, 220, 225, 0.3)'
                         : 'linear-gradient(135deg, #90dce1 0%, #6fc4cc 100%)',
                       boxShadow: '0 8px 20px rgba(144, 220, 225, 0.2)',
                     }}
                   >
                     {downloadVideoLoading ? (
                       <>
                         <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                           <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                           <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                         </svg>
                         {lang === 'zh' ? '准备下载…' : 'Preparing…'}
                       </>
                     ) : (
                       t.downloadMp4
                     )}
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
