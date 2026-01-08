
export interface VideoItem {
  id: string;
  sourceImage: string;
  videoUrl: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress?: number;  // 进度百分比 0-100
  elapsed_time?: number;  // 已运行时间（秒）
  error_msg?: string;
  api_task_id?: string;
}

export interface BatchProgress {
  overall_progress: number;  // 总体进度百分比
  total: number;
  completed: number;
  processing: number;
  pending: number;
  failed: number;
}

export interface Batch {
  id: string;
  userId: string;
  userName: string;
  name: string;
  timestamp: number;
  prompt: string;
  audioName: string;
  imageCount: number;
  items: VideoItem[];
  progress?: BatchProgress;  // 批次进度信息
  creditsUsed?: number;  // 批次消耗的积分
}

export type ViewState = 'create' | 'gallery' | 'admin';

export interface User {
  id: string;
  username: string;
  credits: number;
  isAdmin: boolean;
}
