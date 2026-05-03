"""
分贝监测插件 - 后端服务
基于Flask的REST API服务
功能：接收扣子平台调用，实现分贝监测、录像控制、邮件发送和读取
"""

from flask import Flask, request, jsonify
import smtplib
import imaplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import uuid
from datetime import datetime
import threading

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# WSGI中间件：在请求到达Flask之前处理空JSON问题
class EmptyJsonMiddleware:
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        # 如果Content-Type是application/json
        content_type = environ.get('CONTENT_TYPE', '')
        if 'application/json' in content_type:
            # 检查Content-Length
            content_length = environ.get('CONTENT_LENGTH', '0')
            try:
                if int(content_length) == 0:
                    # body为空，移除Content-Type，让Flask不解析JSON
                    environ['CONTENT_TYPE'] = ''
            except:
                pass
        return self.app(environ, start_response)

# 应用中间件
app.wsgi_app = EmptyJsonMiddleware(app.wsgi_app)

# ============== 配置区域 ==============
# 请修改以下配置为你的实际信息

# 邮件配置（QQ邮箱）
SMTP_SERVER = "smtp.qq.com"  # QQ邮箱SMTP服务器
SMTP_PORT = 587
EMAIL_ADDRESS = "your_email@qq.com"  # 发送邮件的QQ邮箱
EMAIL_PASSWORD = "your_auth_code"    # QQ邮箱授权码（非登录密码，16位）

# 老师邮箱（接收录像邮件的地址）
TEACHER_EMAIL = "teacher@example.com"

# 分贝阈值配置
DECIBEL_THRESHOLD = 70  # 默认70dB

# 录像文件存储目录
VIDEO_DIR = "./videos"

# ============== 内存存储（生产环境建议使用数据库） ==============
monitoring_state = {
    "is_monitoring": False,
    "session_id": None,
    "start_time": None,
    "recordings": [],  # 录像列表 {"video_id": xxx, "start": xxx, "end": xxx, "duration": xxx}
    "threshold": DECIBEL_THRESHOLD,
    "teacher_email": TEACHER_EMAIL
}

# ============== 工具函数 ==============

def generate_session_id():
    """生成会话ID"""
    return str(uuid.uuid4())[:8]

def generate_video_id():
    """生成录像ID"""
    return f"vid_{uuid.uuid4().hex[:8]}"

def save_video_record(video_info):
    """保存录像记录"""
    monitoring_state["recordings"].append(video_info)

def get_record_count():
    """获取当前录像次数"""
    return len(monitoring_state["recordings"])

def get_request_params():
    """统一获取请求参数，同时支持JSON body和URL query"""
    # 先尝试从JSON body获取（安全方式）
    try:
        if request.data and len(request.data.strip()) > 0:
            data = request.get_json()
            if data:
                return data
    except:
        pass  # JSON解析失败，忽略，继续从URL获取
    
    # 如果JSON body为空，从URL query获取
    params = {}
    for key, value in request.args.items():
        # 尝试转换类型
        if value.isdigit():
            params[key] = int(value)
        elif value.replace('.', '', 1).isdigit():
            params[key] = float(value)
        else:
            params[key] = value
    return params

def send_smtp_email(subject, body, to_email, attachments=None):
    """发送邮件"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # 添加正文
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 添加附件（如果有）
        if attachments:
            for file_path in attachments:
                if os.path.exists(file_path):
                    with open(file_path, "rb") as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                        encoders.encode_base64(part)
                        filename = os.path.basename(file_path)
                        part.add_header('Content-Disposition', f'attachment; filename= {filename}')
                        msg.attach(part)
        
        # 发送邮件
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return True, "邮件发送成功"
    except Exception as e:
        return False, f"邮件发送失败: {str(e)}"

def read_latest_email(sender_filter=None):
    """读取最新邮件并返回内容"""
    try:
        # 连接邮箱（QQ邮箱）
        mail = imaplib.IMAP4_SSL("imap.qq.com")  # QQ邮箱IMAP服务器
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select('inbox')
        
        # 搜索邮件
        status, messages = mail.search(None, 'UNSEEN')  # 只读取未读邮件
        # 或者读取所有邮件: mail.search(None, 'ALL')
        
        email_list = messages[0].split()
        
        if not email_list:
            return None, "没有新邮件"
        
        # 获取最新邮件
        latest_email_id = email_list[-1]
        status, msg_data = mail.fetch(latest_email_id, '(RFC822)')
        
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        # 获取发件人
        from_addr = msg['From']
        
        # 过滤发件人（如果指定了）
        if sender_filter and sender_filter.lower() not in from_addr.lower():
            return None, f"没有来自 {sender_filter} 的新邮件"
        
        # 解析邮件内容
        subject = msg['Subject']
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
        else:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        mail.logout()
        
        return {
            "from": from_addr,
            "subject": subject,
            "body": body,
            "date": msg['Date']
        }, "邮件读取成功"
        
    except Exception as e:
        return None, f"邮件读取失败: {str(e)}"

# ============== API 端点 ==============

@app.route('/api/v1/monitor/start', methods=['POST'])
def start_monitor():
    """开始分贝监测"""
    data = get_request_params() or {}
    
    duration = data.get('duration', 0)
    threshold = data.get('threshold', DECIBEL_THRESHOLD)
    
    session_id = generate_session_id()
    monitoring_state["is_monitoring"] = True
    monitoring_state["session_id"] = session_id
    monitoring_state["start_time"] = datetime.now().isoformat()
    monitoring_state["recordings"] = []
    monitoring_state["threshold"] = threshold
    
    # 这里应该连接手机端App获取实时分贝数据
    # 当前返回模拟数据
    current_db = 45.5  # 模拟值，实际应从手机App获取
    
    return jsonify({
        "code": 200,
        "message": "监测已启动",
        "data": {
            "session_id": session_id,
            "current_db": current_db,
            "threshold": threshold,
            "duration": duration
        }
    })

@app.route('/api/v1/monitor/stop', methods=['POST'])
def stop_monitor():
    """停止分贝监测"""
    if not monitoring_state["is_monitoring"]:
        return jsonify({
            "code": 400,
            "message": "当前没有正在进行的监测"
        })
    
    # 计算统计数据
    recordings = monitoring_state["recordings"]
    total_duration = sum(r.get("duration", 0) for r in recordings)
    
    monitoring_state["is_monitoring"] = False
    
    return jsonify({
        "code": 200,
        "message": "监测已停止",
        "data": {
            "session_id": monitoring_state["session_id"],
            "total_duration": total_duration,
            "record_count": len(recordings),
            "max_db": monitoring_state["threshold"],
            "avg_db": monitoring_state["threshold"] - 15  # 模拟值
        }
    })

@app.route('/api/v1/status', methods=['GET'])
def get_status():
    """获取当前分贝状态"""
    record_count = get_record_count()
    
    # 模拟分贝值（实际应从手机端获取）
    current_db = 45.5 if monitoring_state["is_monitoring"] else 0
    
    status = "normal"
    if monitoring_state["is_monitoring"]:
        if current_db > monitoring_state["threshold"]:
            status = "recording"
        elif current_db > monitoring_state["threshold"] - 10:
            status = "warning"
    
    return jsonify({
        "code": 200,
        "message": "成功",
        "data": {
            "is_monitoring": monitoring_state["is_monitoring"],
            "current_db": current_db,
            "threshold": monitoring_state["threshold"],
            "status": status,
            "record_count": record_count
        }
    })

@app.route('/api/v1/video/start', methods=['POST'])
def start_video():
    """开始录像"""
    data = get_request_params() or {}
    reason = data.get('reason', '分贝超标')
    
    video_id = generate_video_id()
    start_time = datetime.now().isoformat()
    
    video_info = {
        "video_id": video_id,
        "start": start_time,
        "end": None,
        "duration": 0,
        "reason": reason,
        "status": "recording"
    }
    save_video_record(video_info)
    
    return jsonify({
        "code": 200,
        "message": "录像已开始",
        "data": {
            "video_id": video_id,
            "start_time": start_time,
            "reason": reason
        }
    })

@app.route('/api/v1/video/stop', methods=['POST'])
def stop_video():
    """停止录像"""
    data = get_request_params() or {}
    video_id = data.get('video_id')
    
    # 找到当前录像并更新
    recordings = monitoring_state["recordings"]
    target_video = None
    
    for video in reversed(recordings):  # 逆序查找最近的
        if video.get("status") == "recording":
            target_video = video
            break
    
    if not target_video:
        return jsonify({
            "code": 400,
            "message": "没有正在录像的任务"
        })
    
    # 更新录像信息
    target_video["end"] = datetime.now().isoformat()
    target_video["status"] = "saved"
    # 计算时长（模拟）
    target_video["duration"] = 30  # 模拟30秒
    
    return jsonify({
        "code": 200,
        "message": "录像已保存",
        "data": {
            "video_id": target_video["video_id"],
            "duration": target_video["duration"],
            "file_path": f"{VIDEO_DIR}/{target_video['video_id']}.mp4"
        }
    })

@app.route('/api/v1/video/send', methods=['POST'])
def send_video_email():
    """发送录像邮件给老师"""
    data = get_request_params() or {}
    teacher_email = data.get('teacher_email') or data.get('to_email') or monitoring_state["teacher_email"]
    session_summary = data.get('session_summary', '')
    
    recordings = monitoring_state["recordings"]
    
    if not recordings:
        return jsonify({
            "code": 400,
            "message": "没有录像可供发送"
        })
    
    # 准备邮件内容
    subject = f"课堂监测录像报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    body = f"""
您好，

以下是本次课堂监测的录像记录：

监测时间：{monitoring_state.get('start_time', 'N/A')}
录像次数：{len(recordings)}次
分贝阈值：{monitoring_state['threshold']}dB

{session_summary}

请查收附件中的录像文件。

此致
分贝监测系统
"""
    
    # 收集录像文件（如果有）
    attachments = []
    for video in recordings:
        file_path = f"{VIDEO_DIR}/{video['video_id']}.mp4"
        if os.path.exists(file_path):
            attachments.append(file_path)
    
    # 发送邮件
    success, msg = send_smtp_email(subject, body, teacher_email, attachments)
    
    if success:
        return jsonify({
            "code": 200,
            "message": "邮件已发送",
            "data": {
                "email_id": generate_session_id(),
                "attachments": attachments,
                "recipient": teacher_email
            }
        })
    else:
        return jsonify({
            "code": 500,
            "message": msg
        })

@app.route('/api/v1/email/read', methods=['POST'])
def read_email():
    """读取邮件并返回内容（供语音播放）"""
    data = get_request_params() or {}
    sender_filter = data.get('sender_filter', '')
    
    email_content, msg = read_latest_email(sender_filter)
    
    if email_content:
        # 合并主题和正文，供TTS播放
        full_text = f"收到新邮件，主题：{email_content['subject']}，内容：{email_content['body']}"
        
        return jsonify({
            "code": 200,
            "message": "邮件已读取",
            "data": {
                "subject": email_content["subject"],
                "content": email_content["body"],
                "full_text": full_text,  # 合并后的文本，适合TTS播放
                "from": email_content["from"],
                "is_played": True
            }
        })
    else:
        return jsonify({
            "code": 200,
            "message": msg,
            "data": None
        })

@app.route('/api/v1/config/threshold', methods=['GET', 'POST'])
def config_threshold():
    """获取或设置分贝阈值"""
    if request.method == 'GET':
        return jsonify({
            "code": 200,
            "data": {
                "threshold": monitoring_state["threshold"],
                "unit": "dB"
            }
        })
    else:
        data = get_request_params() or {}
        threshold = data.get('threshold', 70)
        monitoring_state["threshold"] = threshold
        
        return jsonify({
            "code": 200,
            "message": f"阈值已更新为 {threshold}dB",
            "data": {
                "threshold": threshold
            }
        })

@app.route('/api/v1/config/teacher', methods=['GET', 'POST'])
def config_teacher():
    """获取或设置老师邮箱"""
    if request.method == 'GET':
        return jsonify({
            "code": 200,
            "data": {
                "email": monitoring_state["teacher_email"]
            }
        })
    else:
        data = get_request_params() or {}
        email = data.get('email')
        if email:
            monitoring_state["teacher_email"] = email
            return jsonify({
                "code": 200,
                "message": "老师邮箱已设置",
                "data": {
                    "email": email
                }
            })
        else:
            return jsonify({
                "code": 400,
                "message": "邮箱地址不能为空"
            })

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

# ============== 主程序 ==============

if __name__ == '__main__':
    # 确保录像目录存在
    os.makedirs(VIDEO_DIR, exist_ok=True)
    
    print("=" * 50)
    print("分贝监测后端服务启动")
    print(f"SMTP服务器: {SMTP_SERVER}")
    print(f"发送邮箱: {EMAIL_ADDRESS}")
    print(f"老师邮箱: {TEACHER_EMAIL}")
    print(f"分贝阈值: {DECIBEL_THRESHOLD}dB")
    print("=" * 50)
    
    # 启动服务
    app.run(host='0.0.0.0', port=5000, debug=True)
