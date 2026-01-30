/**
 * API 客户端 - 处理所有后端 API 调用
 */

const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000';

// 从 localStorage 获取 token
function getToken(): string | null {
  return localStorage.getItem('token');
}

// 设置 token
function setToken(token: string): void {
  localStorage.setItem('token', token);
}

// 清除 token
function clearToken(): void {
  localStorage.removeItem('token');
}

// 通用请求函数
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Token 过期，清除并跳转到登录
    clearToken();
    window.location.reload();
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// 文件上传请求
async function uploadRequest<T>(
  endpoint: string,
  formData: FormData
): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {};

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (response.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// ==================== 认证 API ====================

export interface LoginResponse {
  token: string;
  user_info: {
    id: string;
    username: string;
    credits: number;
    isAdmin: boolean;
  };
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const formData = new FormData();
  formData.append('username', username);
  formData.append('password', password);
  
  // 登录接口需要特殊处理，401 不应该清除 token 和重载页面
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: {},
    body: formData,
  });

  // 检查响应类型
  const contentType = response.headers.get('content-type');
  const isJson = contentType && contentType.includes('application/json');

  // 登录接口的 401 不应该清除 token 和重载页面，应该显示错误
  if (!response.ok) {
    if (isJson) {
      try {
        const error = await response.json();
        // 优先使用后端返回的详细错误信息
        const errorMessage = error.detail || error.message || `HTTP ${response.status}`;
        throw new Error(errorMessage);
      } catch (e) {
        if (e instanceof Error && !e.message.includes('JSON')) {
          // 如果已经是解析好的错误，直接抛出
          throw e;
        }
        // 如果解析失败，根据状态码返回友好的错误信息
        if (response.status === 401) {
          throw new Error('Invalid username or password');
        }
        throw new Error(`Login failed: HTTP ${response.status}`);
      }
    } else {
      // 如果返回的不是 JSON，可能是 HTML 错误页面
      const text = await response.text();
      console.error('Non-JSON response:', text.substring(0, 200));
      if (response.status === 401) {
        throw new Error('Invalid username or password');
      }
      throw new Error(`Server returned non-JSON response. Check API_BASE: ${API_BASE}`);
    }
  }

  // 响应成功，解析 JSON
  if (!isJson) {
    throw new Error('Server returned non-JSON response');
  }

  const data = await response.json();
  setToken(data.token);
  return data;
}

// ==================== 用户 API ====================

export interface User {
  id: string;
  username: string;
  credits: number;
  isAdmin: boolean;
}

export async function getProfile(): Promise<User> {
  return request<User>('/api/user/profile');
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  const formData = new FormData();
  formData.append('old_password', oldPassword);
  formData.append('new_password', newPassword);
  
  const token = getToken();
  const headers: HeadersInit = {};

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/api/user/change-password`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (response.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to change password' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  await response.json();
}

// ==================== 批次 API ====================

export interface VideoItem {
  id: string;
  sourceImage: string;
  videoUrl: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  error_msg?: string;
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
}

export interface CreateBatchResponse {
  batch_id: string;
}

export async function createBatch(
  images: File[],
  audio: File,
  prompt: string
): Promise<CreateBatchResponse> {
  const formData = new FormData();
  
  // 添加所有图片
  images.forEach((img) => {
    formData.append('images', img);
  });
  
  // 添加音频
  formData.append('audio', audio);
  
  // 添加提示词
  formData.append('prompt', prompt);
  
  return uploadRequest<CreateBatchResponse>('/api/video/batch', formData);
}

export interface GetBatchesResponse {
  batches: Batch[];
  total: number;
}

export async function getBatches(limit: number = 50, offset: number = 0): Promise<GetBatchesResponse> {
  return request<GetBatchesResponse>(`/api/video/batches?limit=${limit}&offset=${offset}`);
}

export async function getBatch(batchId: string): Promise<Batch> {
  return request<Batch>(`/api/video/batches/${batchId}`);
}

export async function cancelBatchItem(batchId: string, itemId: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/api/video/batches/${batchId}/items/${itemId}/cancel`,
    { method: 'POST' }
  );
}

export async function resumeBatchItem(batchId: string, itemId: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/api/video/batches/${batchId}/items/${itemId}/resume`,
    { method: 'POST' }
  );
}

export async function retryFailedBatchItems(batchId: string): Promise<{ success: boolean; count: number }> {
  return request<{ success: boolean; count: number }>(
    `/api/video/batches/${batchId}/retry_failed`,
    { method: 'POST' }
  );
}

// ==================== 管理员 API ====================

export interface GetAllUsersResponse {
  users: User[];
}

export async function getAllUsers(): Promise<GetAllUsersResponse> {
  return request<GetAllUsersResponse>('/api/admin/users');
}

export interface CreateUserResponse {
  success: boolean;
  user: User;
}

export async function createUser(username: string, credits: number = 100, is_admin: boolean = false): Promise<CreateUserResponse> {
  const formData = new FormData();
  formData.append('username', username);
  formData.append('credits', credits.toString());
  formData.append('is_admin', is_admin.toString());
  
  const token = getToken();
  const headers: HeadersInit = {};

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/api/admin/users`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (response.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to create user' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function updateUserCredits(userId: string, newCredits: number): Promise<void> {
  const formData = new FormData();
  formData.append('new_credits', newCredits.toString());
  
  const token = getToken();
  const headers: HeadersInit = {};

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/api/admin/users/${userId}/credits`, {
    method: 'PATCH',
    headers,
    body: formData,
  });

  if (response.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  await response.json();
}

export interface UpdateTokenResponse {
  success: boolean;
  message: string;
  warning?: string;
}

export async function updateS2VToken(newToken: string): Promise<UpdateTokenResponse> {
  const formData = new FormData();
  formData.append('new_token', newToken);
  
  const token = getToken();
  const headers: HeadersInit = {};

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/api/admin/token`, {
    method: 'PATCH',
    headers,
    body: formData,
  });

  if (response.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to update token' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export interface GetAllBatchesResponse {
  batches: Batch[];
  total: number;
}

export async function getAllBatches(limit: number = 100, offset: number = 0): Promise<GetAllBatchesResponse> {
  return request<GetAllBatchesResponse>(`/api/admin/batches?limit=${limit}&offset=${offset}`);
}

// ==================== 工具函数 ====================

export function getFileUrl(filenameOrPath: string, subdir: string = 'images'): string {
  if (!filenameOrPath) {
    return '';
  }
  
  // 如果已经是完整 URL，直接返回
  if (filenameOrPath.startsWith('http://') || filenameOrPath.startsWith('https://')) {
    return filenameOrPath;
  }
  
  // 如果已经是相对路径（以 /api/files 开头），需要编码文件名部分
  if (filenameOrPath.startsWith('/api/files/')) {
    // 提取路径和文件名
    const parts = filenameOrPath.split('/');
    if (parts.length >= 4) {
      // /api/files/subdir/filename
      const subdirPart = parts[3];
      const filename = parts.slice(4).join('/'); // 处理可能包含 / 的文件名
      // 只编码文件名部分，不编码路径部分
      const encodedFilename = encodeURIComponent(filename);
      return `${API_BASE}/api/files/${subdirPart}/${encodedFilename}`;
    }
    return `${API_BASE}${filenameOrPath}`;
  }
  
  // 否则，假设是文件名，构建完整路径并编码文件名
  // 对文件名进行 URL 编码，处理空格和特殊字符
  const encodedFilename = encodeURIComponent(filenameOrPath);
  return `${API_BASE}/api/files/${subdir}/${encodedFilename}`;
}

// 检查 S2V API token 状态
export async function checkTokenStatus(): Promise<{ valid: boolean; error?: string }> {
  return request<{ valid: boolean; error?: string }>('/api/token/status');
}

export interface ExportFile {
  name: string;
  url: string;
  id: string;
}

export interface ExportBatchResponse {
  batch_id: string;
  batch_name: string;
  files: ExportFile[];
  total: number;
}

// 获取批次的所有已完成视频下载清单
export async function getBatchExportList(batchId: string): Promise<ExportBatchResponse> {
  const token = getToken();
  if (!token) {
    throw new Error('Not authenticated');
  }

  const response = await fetch(`${API_BASE}/api/video/batches/${batchId}/export`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (response.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// 批量下载文件（前端直接下载，不经过后端）
export async function batchDownloadFiles(files: ExportFile[], onProgress?: (current: number, total: number) => void): Promise<void> {
  // 并发下载，限制并发数为 4
  const limit = 4;
  let currentIndex = 0;
  let completedCount = 0;
  const total = files.length;

  async function downloadOne(file: ExportFile): Promise<void> {
    const a = document.createElement('a');
    // 如果是相对路径，补全为完整 URL
    const url = file.url.startsWith('http') ? file.url : `${API_BASE}${file.url}`;
    a.href = url;
    a.download = file.name;
    a.rel = 'noopener noreferrer';
    a.style.display = 'none';
    a.target = '_blank'; // 某些浏览器需要这个
    
    document.body.appendChild(a);
    a.click();
    
    // 延迟移除，确保点击事件被触发
    setTimeout(() => {
      document.body.removeChild(a);
    }, 100);
    
    completedCount++;
    if (onProgress) {
      onProgress(completedCount, total);
    }
    
    // 给浏览器一点喘息空间，防止被判定为恶意下载
    await new Promise(resolve => setTimeout(resolve, 200));
  }

  async function worker(): Promise<void> {
    while (currentIndex < files.length) {
      const file = files[currentIndex++];
      await downloadOne(file);
    }
  }

  // 启动多个 worker 并发下载
  await Promise.all(Array.from({ length: Math.min(limit, files.length) }, () => worker()));
}

export { clearToken, getToken };

