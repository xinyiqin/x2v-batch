# 智影 AI (AI Vision) - 后端对接开发文档

本前端项目是一个基于 React 的 AI 数字人批量视频生成平台。目前前端已完成交互逻辑、UI 设计、点数消耗模拟以及管理端逻辑。

## 1. 项目当前功能 (Frontend Features)

### 1.1 用户端功能
- **鉴权系统**：支持用户名/密码登录（当前为 Mock 逻辑，admin 账号默认拥有管理权限）。
- **点数系统**：
    - 每生成 1 张图片对应的视频消耗 1 点。
    - 余额不足时自动拦截生成请求。
    - 个人余额在侧边栏实时展示。
- **批量任务创建**：
    - 支持上传最多 50 张图片。
    - 支持上传参考音频（MP3/WAV）。
    - 支持选填生成提示词（描述表情、动作等）。
- **结果查看**：
    - 自动按批次（文件夹形式）归档。
    - 瀑布流展示生成后的视频预览图。
    - 弹窗模拟视频播放。

### 1.2 管理端功能
- **用户管理**：查看系统中所有用户的当前点数。
- **点数调整**：管理员可手动增减特定用户的点数。
- **全局记录**：查看系统内所有用户产生的生成任务历史记录。

---

## 2. 推荐数据库结构 (Proposed Database Schema)

### 2.1 Users (用户表)
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | UUID / String | 唯一标识 |
| `username` | String | 用户名（唯一） |
| `password_hash` | String | 加密后的密码 |
| `credits` | Integer | 剩余点数（默认 0 或 100） |
| `is_admin` | Boolean | 是否为管理员 |
| `created_at` | Timestamp | 注册时间 |

### 2.2 Batches (任务批次表)
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | UUID / String | 批次 ID |
| `user_id` | String | 所属用户 ID |
| `name` | String | 批次名称（如：批次 2023-10-27） |
| `prompt` | Text | 生成提示词 |
| `audio_url` | String | 存储在对象存储中的音频 URL |
| `image_count` | Integer | 图片总数（消耗点数参考） |
| `created_at` | Timestamp | 创建时间 |

### 2.3 VideoItems (视频子项表)
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | UUID / String | 唯一标识 |
| `batch_id` | String | 所属批次 ID |
| `source_image_url` | String | 源图片 URL |
| `video_url` | String | 生成后的视频结果 URL |
| `status` | Enum | 状态: `pending`, `processing`, `completed`, `failed` |
| `error_msg` | String | 失败时的错误描述 |

---

## 3. 后端 API 接口需求 (Backend API Requirements)

### 3.1 鉴权模块
- `POST /api/auth/login`
    - 输入：`username`, `password`
    - 返回：`token`, `user_info` (id, username, credits, isAdmin)

### 3.2 用户模块
- `GET /api/user/profile`
    - 获取当前用户的最新点数和信息。

### 3.3 视频生成模块
- `POST /api/video/batch` (Multipart Form Data 或 JSON 配合预签名 URL)
    - 输入：`images[]`, `audio`, `prompt`
    - 逻辑：后端需校验用户 `credits` 是否充足。若充足，扣除点数并启动异步 AI 生成任务。
    - 返回：`batch_id`
- `GET /api/video/batches`
    - 获取当前用户的历史批次列表（分页）。
- `GET /api/video/batches/:id`
    - 获取特定批次下的所有视频子项状态及结果。

### 3.4 管理员模块 (需校验 isAdmin)
- `GET /api/admin/users`
    - 返回所有用户列表及点数。
- `PATCH /api/admin/users/:id/credits`
    - 输入：`new_credits`
    - 功能：管理员手动重置或增减用户点数。
- `GET /api/admin/batches`
    - 获取全系统的任务流水记录。

---

## 4. 前端对接指南 (Frontend Integration)

1.  **API 地址配置**：在 `App.tsx` 或专门的 `api.ts` 中替换目前的 `setTimeout` 模拟逻辑为实际的 `fetch` 或 `axios` 调用。
2.  **文件处理**：目前图片使用 `URL.createObjectURL` 展示，实际对接时需将 File 对象通过 FormData 发送或先调用预签名上传接口。
3.  **状态轮询**：对于生成中的视频，前端 `BatchGallery` 组件建议增加轮询逻辑（每 5-10 秒请求一次结果），直到 `status` 变为 `completed`。
4.  **Token 存储**：登录成功后将 JWT Token 存入 `localStorage`，并在后续请求头中带上 `Authorization: Bearer <token>`。

---
*文档由前端工程师提供，旨在明确前后端数据交互边界。*
