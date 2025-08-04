import os
import asyncio
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from datetime import datetime
import logging
from client import MCPClient  # 导入客户端类

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("flask_app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("flask_app")

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['UPLOAD_FOLDER'] = './uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB上限

# 确保上传文件夹存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'txt', 'md', 'png', 'jpg', 'jpeg'}

# 检查文件扩展名是否允许
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 运行异步任务的辅助函数
def run_async_task(coroutine):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()

# 创建MCP客户端实例
mcp_client = None

def init_mcp_client():
    global mcp_client
    if mcp_client is None:
        mcp_client = MCPClient()
        try:
            server_script_path = os.path.join("server.py")
            run_async_task(mcp_client.connect_to_server(server_script_path))
            logger.info("MCP client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {str(e)}")
            mcp_client = None
    return mcp_client

# 路由定义
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/query', methods=['POST'])
def process_query():
    if request.method == 'POST':
        query = request.form.get('query', '')
        if not query:
            return jsonify({'success': False, 'error': '查询不能为空'})
            
        # 初始化MCP客户端
        client = init_mcp_client()
        if client is None:
            return jsonify({'success': False, 'error': 'Failed to initialize MCP client'})
            
        # 运行异步查询处理
        try:
            result = run_async_task(client.process_query(query))
            return jsonify({'success': True, 'response': result})
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

@app.route('/send_email', methods=['POST'])
def send_email():
    if request.method == 'POST':
        to_email = request.form.get('to_email', '')
        subject = request.form.get('subject', 'MCP系统邮件')
        body = request.form.get('body', '这是一封来自MCP系统的邮件')
        file_path = request.form.get('file_path', '')
        
        if not to_email or not file_path:
            return jsonify({'success': False, 'error': '收件人和文件路径不能为空'})
            
        # 初始化MCP客户端
        client = init_mcp_client()
        if client is None:
            return jsonify({'success': False, 'error': 'Failed to initialize MCP client'})
            
        # 运行异步邮件发送
        try:
            # 注意：原client.py中没有直接的send_email方法，需要调用process_query来触发邮件发送
            query = f"发送邮件到{to_email}，主题：{subject}，正文：{body}，附件：{file_path}"
            result = run_async_task(client.process_query(query))
            return jsonify({'success': True, 'message': result})
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('没有文件部分')
        return redirect(request.url)
        
    file = request.files['file']
    if file.filename == '':
        flash('没有选择文件')
        return redirect(request.url)
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return jsonify({'success': True, 'file_path': filepath})
    else:
        return jsonify({'success': False, 'error': '不支持的文件类型'})

@app.route('/list_files')
def list_files():
    output_dir = './llm_outputs'
    if not os.path.exists(output_dir):
        return jsonify({'success': False, 'error': '输出目录不存在'})
        
    files = []
    for filename in os.listdir(output_dir):
        filepath = os.path.join(output_dir, filename)
        if os.path.isfile(filepath):
            files.append({
                'name': filename,
                'path': filepath,
                'size': os.path.getsize(filepath),
                'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
            })
    
    # 按修改时间排序
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'success': True, 'files': files})

@app.route('/view_file/<filename>')
def view_file(filename):
    output_dir = './llm_outputs'
    filepath = os.path.join(output_dir, filename)
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'error': '文件不存在'})
        
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'success': True, 'content': content})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/stop_server')
def stop_server():
    global mcp_client
    if mcp_client:
        try:
            run_async_task(mcp_client.cleanup())
            mcp_client = None
            logger.info("MCP client stopped")
        except Exception as e:
            logger.error(f"Error stopping MCP client: {str(e)}")
    return jsonify({'success': True, 'message': 'Server stopped'})

if __name__ == '__main__':
    # 确保templates文件夹存在
    os.makedirs('templates', exist_ok=True)
    # 启动Flask应用
    app.run(debug=True, host='0.0.0.0', port=5000)