#!/usr/bin/env python3
"""
最简单的HTTP服务器，完全绕过Flask的JSON解析问题
直接从URL读取所有参数，不碰body
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import uuid
from datetime import datetime
import os
import smtplib
import imaplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ============ 配置 ============
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 587
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
TEACHER_EMAIL = os.environ.get("TEACHER_EMAIL", "")

# ============ 全局状态 ============
monitoring_state = {
    "is_monitoring": False,
    "session_id": None,
    "start_time": None,
    "recordings": [],
    "threshold": 70,
    "teacher_email": TEACHER_EMAIL
}

# ============ 工具函数 ============
def generate_session_id():
    return str(uuid.uuid4())[:8]

def generate_video_id():
    return f"vid_{uuid.uuid4().hex[:8]}"

def get_record_count():
    return len(monitoring_state["recordings"])

# ============ API处理函数 ============
def api_monitor_start(params):
    """开始监测"""
    duration = int(params.get('duration', ['0'])[0])
    threshold = float(params.get('threshold', ['70'])[0])
    
    session_id = generate_session_id()
    monitoring_state["is_monitoring"] = True
    monitoring_state["session_id"] = session_id
    monitoring_state["start_time"] = datetime.now().isoformat()
    monitoring_state["recordings"] = []
    monitoring_state["threshold"] = threshold
    
    return {
        "code": 200,
        "message": "监测已启动",
        "data": {
            "session_id": session_id,
            "current_db": 45.5,
            "threshold": threshold,
            "duration": duration
        }
    }

def api_monitor_stop(params):
    """停止监测"""
    if not monitoring_state["is_monitoring"]:
        return {"code": 400, "message": "当前没有正在进行的监测"}
    
    recordings = monitoring_state["recordings"]
    total_duration = sum(r.get("duration", 0) for r in recordings)
    monitoring_state["is_monitoring"] = False
    
    return {
        "code": 200,
        "message": "监测已停止",
        "data": {
            "session_id": monitoring_state["session_id"],
            "total_duration": total_duration,
            "record_count": len(recordings),
            "max_db": monitoring_state["threshold"],
            "avg_db": monitoring_state["threshold"] - 15
        }
    }

def api_get_status(params):
    """获取状态"""
    record_count = get_record_count()
    current_db = 45.5 if monitoring_state["is_monitoring"] else 0
    
    status = "normal"
    if monitoring_state["is_monitoring"]:
        if current_db > monitoring_state["threshold"]:
            status = "recording"
        elif current_db > monitoring_state["threshold"] - 10:
            status = "warning"
    
    return {
        "code": 200,
        "message": "成功",
        "data": {
            "is_monitoring": monitoring_state["is_monitoring"],
            "current_db": current_db,
            "threshold": monitoring_state["threshold"],
            "status": status,
            "record_count": record_count
        }
    }

def api_video_start(params):
    """开始录像"""
    reason = params.get('reason', ['分贝超标'])[0]
    
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
    monitoring_state["recordings"].append(video_info)
    
    return {
        "code": 200,
        "message": "录像已开始",
        "data": {
            "video_id": video_id,
            "start_time": start_time,
            "reason": reason
        }
    }

def api_video_stop(params):
    """停止录像"""
    video_id = params.get('video_id', [None])[0]
    
    target_video = None
    for video in reversed(monitoring_state["recordings"]):
        if video.get("status") == "recording":
            target_video = video
            break
    
    if not target_video:
        return {"code": 400, "message": "没有正在录像的任务"}
    
    target_video["end"] = datetime.now().isoformat()
    target_video["status"] = "saved"
    target_video["duration"] = 30
    
    return {
        "code": 200,
        "message": "录像已停止",
        "data": {
            "video_id": target_video["video_id"],
            "end_time": target_video["end"],
            "duration": 30
        }
    }

def api_send_email(params):
    """发送邮件"""
    teacher_email = params.get('teacher_email', [None])[0] or params.get('to_email', [None])[0] or monitoring_state["teacher_email"]
    subject = params.get('subject', ['课堂噪音监测报告'])[0]
    body = params.get('body', ['这是一封测试邮件'])[0]
    
    if not teacher_email:
        return {"code": 400, "message": "请指定收件人邮箱"}
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = teacher_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return {"code": 200, "message": "邮件发送成功"}
    except Exception as e:
        return {"code": 500, "message": f"邮件发送失败: {str(e)}"}

def api_read_email(params):
    """读取邮件"""
    sender_filter = params.get('sender_filter', [''])[0]
    
    try:
        mail = imaplib.IMAP4_SSL("imap.qq.com")
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select('inbox')
        
        status, messages = mail.search(None, 'UNSEEN')
        email_list = messages[0].split()
        
        if not email_list:
            return {"code": 200, "message": "没有新邮件", "data": None}
        
        latest_email_id = email_list[-1]
        status, msg_data = mail.fetch(latest_email_id, '(RFC822)')
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        from_addr = msg['From']
        if sender_filter and sender_filter.lower() not in from_addr.lower():
            return {"code": 200, "message": f"没有来自 {sender_filter} 的新邮件", "data": None}
        
        subject = msg['Subject']
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
        else:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        mail.logout()
        
        return {
            "code": 200,
            "message": "邮件读取成功",
            "data": {
                "from": from_addr,
                "subject": subject,
                "body": body,
                "date": msg['Date']
            }
        }
    except Exception as e:
        return {"code": 500, "message": f"邮件读取失败: {str(e)}"}

def api_config_threshold(params):
    """设置/获取阈值"""
    if 'threshold' in params:
        threshold = float(params.get('threshold', ['70'])[0])
        monitoring_state["threshold"] = threshold
        return {
            "code": 200,
            "message": "阈值已更新",
            "data": {"threshold": threshold}
        }
    else:
        return {
            "code": 200,
            "message": "成功",
            "data": {"threshold": monitoring_state["threshold"]}
        }

def api_config_teacher(params):
    """设置/获取老师邮箱"""
    if 'email' in params or 'teacher_email' in params:
        email = params.get('email', [None])[0] or params.get('teacher_email', [None])[0]
        if email:
            monitoring_state["teacher_email"] = email
            return {
                "code": 200,
                "message": "老师邮箱已更新",
                "data": {"email": email}
            }
    return {
        "code": 200,
        "message": "成功",
        "data": {"email": monitoring_state["teacher_email"]}
    }

# ============ 路由映射 ============
ROUTES = {}

def api_root(params):
    return {
        "code": 200,
        "message": "分贝监测后端服务运行正常！",
        "data": {
            "available_apis": list(ROUTES.keys())
        }
    }

ROUTES['/'] = api_root
ROUTES['/api/v1/monitor/start'] = api_monitor_start
ROUTES['/api/v1/monitor/stop'] = api_monitor_stop
ROUTES['/api/v1/status'] = api_get_status
ROUTES['/api/v1/video/start'] = api_video_start
ROUTES['/api/v1/video/stop'] = api_video_stop
ROUTES['/api/v1/video/send'] = api_send_email
ROUTES['/api/v1/email/read'] = api_read_email
ROUTES['/api/v1/config/threshold'] = api_config_threshold
ROUTES['/api/v1/config/teacher'] = api_config_teacher

# ============ HTTP请求处理器 ============
class RequestHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_OPTIONS(self):
        self._set_headers()
    
    def do_GET(self):
        self.handle_request('GET')
    
    def do_POST(self):
        self.handle_request('POST')
    
    def handle_request(self, method):
        try:
            # 解析URL和参数
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)
            
            # 路由匹配
            if path in ROUTES:
                result = ROUTES[path](params)
                self._set_headers(result.get('code', 200))
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({
                    "code": 404,
                    "message": f"接口不存在: {path}"
                }, ensure_ascii=False).encode('utf-8'))
        
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({
                "code": 500,
                "message": f"服务器错误: {str(e)}"
            }, ensure_ascii=False).encode('utf-8'))
    
    def log_message(self, format, *args):
        # 禁用默认日志
        pass

# ============ 启动服务器 ============
def run(server_class=HTTPServer, handler_class=RequestHandler, port=8000):
    server_address = ('0.0.0.0', port)
    httpd = server_class(server_address, handler_class)
    print(f"服务器启动成功，监听端口: {port}")
    print(f"可用接口:")
    for path in ROUTES:
        print(f"  - {path}")
    httpd.serve_forever()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    run(port=port)
