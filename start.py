import os
import sys
import asyncio
import subprocess
import time
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def check_env_vars():
    """检查必要的环境变量是否已设置"""
    required_vars = ["QWEN_API_KEY", "BASE_URL", "MODEL", "GOOGLE_API_KEY", "SMTP_SERVER", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"错误: 缺少必要的环境变量: {', '.join(missing_vars)}")
        return False
    return True

async def start_server():
    print("Starting server...")
    # 启动服务器进程
    server_process = subprocess.Popen(
        [sys.executable, "server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return server_process

async def monitor_server(server_process):
    """监控服务器输出并打印详细日志"""
    try:
        # 读取标准输出
        stdout_lines = []
        while True:
            if server_process.stdout.closed:
                break
            line = server_process.stdout.readline()
            if not line:
                break
            stdout_lines.append(line.strip())
            print(f"Server output: {line.strip()}")

        # 读取标准错误
        stderr_lines = []
        while True:
            if server_process.stderr.closed:
                break
            line = server_process.stderr.readline()
            if not line:
                break
            stderr_lines.append(line.strip())
            print(f"Server error: {line.strip()}")

        return stdout_lines, stderr_lines
    except Exception as e:
        print(f"Error monitoring server: {e}")
        return [], [str(e)]

async def main():
    # 检查环境变量
    if not check_env_vars():
        return

    # 先启动服务器
    server_process = await start_server()

    # 启动监控服务器输出的任务
    server_monitor_task = asyncio.create_task(monitor_server(server_process))

    # 等待服务器启动
    print("Waiting for server to start...")
    time.sleep(5)  # 增加等待时间

    # 检查服务器是否还在运行
    server_status = server_process.poll()
    if server_status is not None:
        print(f"Server has exited with code: {server_status}")
        # 获取服务器输出
        stdout_lines, stderr_lines = await server_monitor_task
        print("\nServer output lines:")
        for line in stdout_lines:
            print(f"  {line}")
        print("\nServer error lines:")
        for line in stderr_lines:
            print(f"  {line}")
        return
    else:
        print("Server is still running")

    # 如果服务器仍在运行，提示用户手动运行客户端
    print("\nServer is running. You can now run the client manually with:")
    print("  python client.py")
    print("\nPress Ctrl+C to stop the server...")

    # 等待用户中断
    try:
        while server_process.poll() is None:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        # 停止服务器
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

if __name__ == "__main__":
    # 确保使用正确的事件循环
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error running main: {e}")
        import traceback
        traceback.print_exc()