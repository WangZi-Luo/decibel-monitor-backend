[README.md](https://github.com/user-attachments/files/27304185/README.md)
# 分贝监测后端服务

基于 Flask 的 REST API 服务，接收扣子平台插件调用。

## 功能

- ✅ 分贝监测（开始/停止/状态查询）
- ✅ 录像控制（开始/停止）
- ✅ 邮件发送（录像记录发送给老师）
- ✅ 邮件读取（获取老师邮件内容供语音播放）

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置邮箱

编辑 `app.py`，修改配置区域：

```python
# 邮件配置
SMTP_SERVER = "smtp.gmail.com"  # 或 smtp.qq.com
SMTP_PORT = 587
EMAIL_ADDRESS = "your_email@gmail.com"  # 发送邮件的邮箱
EMAIL_PASSWORD = "your_app_password"    # 邮箱授权码

# 老师邮箱
TEACHER_EMAIL = "teacher@example.com"

# 分贝阈值
DECIBEL_THRESHOLD = 70
```

### 3. 启动服务

```bash
python app.py
```

服务将在 `http://0.0.0.0:5000` 启动

### 4. 测试接口

```bash
# 健康检查
curl http://localhost:5000/health

# 获取状态
curl http://localhost:5000/api/v1/status

# 开始监测
curl -X POST http://localhost:5000/api/v1/monitor/start \
  -H "Content-Type: application/json" \
  -d '{"duration": 45, "threshold": 70}'
```

## API 列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/monitor/start` | POST | 开始分贝监测 |
| `/api/v1/monitor/stop` | POST | 停止分贝监测 |
| `/api/v1/status` | GET | 获取当前状态 |
| `/api/v1/video/start` | POST | 开始录像 |
| `/api/v1/video/stop` | POST | 停止录像 |
| `/api/v1/video/send` | POST | 发送录像邮件 |
| `/api/v1/email/read` | POST | 读取邮件 |
| `/api/v1/config/threshold` | GET/POST | 获取/设置阈值 |
| `/api/v1/config/teacher` | GET/POST | 获取/设置老师邮箱 |

## 部署到云端

### 方案1：阿里云函数计算

1. 创建函数
2. 上传代码
3. 配置环境变量
4. 设置触发器为HTTP

### 方案2：腾讯云SCF

类似阿里云函数计算

### 方案3：Railway / Render

支持Python，一键部署

### 方案4：自己的服务器

```bash
# 使用 uwsgi + nginx
pip install uwsgi
uwsgi --http :5000 --wsgi-file app.py --master --processes 4 --threads 2
```

## 注意事项

1. **邮件授权码**：
   - Gmail: 需要应用专用密码
   - QQ邮箱: 设置 → 账户 → POP3/SMTP服务 → 生成授权码

2. **公网访问**：扣子平台需要公网可访问的URL，建议使用云函数或内网穿透

3. **手机端集成**：真正的分贝监测需要在Android/iOS端实现，通过HTTP上报数据
