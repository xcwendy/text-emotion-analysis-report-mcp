import os
from openai import OpenAI
from mcp.server.fastmcp import FastMCP
from datetime import datetime
from dotenv import load_dotenv
import json
import httpx
import smtplib
import os
from email.message import EmailMessage

load_dotenv()

#初始化mcp服务器
mcp = FastMCP("mcp-server")

@mcp.tool()
async def search_google(query: str) -> str:
    """使用Google搜索"""
    #这里可以调用Google API进行搜索
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set.") 
    url = "https://serpapi.com/search?engine=google_news"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    payload = {"q": query}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        data = response.json()
    
    if "news" not in data:
        return "没有找到相关的新闻。"

    articles = [
        {
            "title": article.get("title"),
            "link": article.get("link"),
            "snippet": article.get("snippet")
        } for article in data["news"][:5]  # 获取前5条新闻
    ]

    output_dir = "./google_news"
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    file_path = os.path.join(output_dir,filename)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    return (
        f"已找到与'{query}'相关的前五条新闻：\n"
        f"{json.dumps(articles, ensure_ascii=False, indent=2)}\n"
        f"详细信息已保存到 {file_path}。"
    )



@mcp.tool()
async def analyze_sentiment(text: str) -> str:
    """分析文本情感"""
    #这里可以调用情感分析API
    api_key = os.getenv("QWEN_API_KEY")
    model = os.getenv("MODEL")
    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("BASE_URL"),
        model=model
    )
    prompt = f"请分析以下文本的情感倾向，并说明原因：\n\n{text}"
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个情感分析助手。"},
            {"role": "user", "content": prompt}
        ]
    )
    result =response.choices[0].message.content.strip()

    markdown = f""" # 情感分析报告

{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
## 用户输入
{text}

---
## 分析结果
{result}
"""
    output_dir = "./sentiment_analysis"
    os.makedirs(output_dir, exist_ok=True)

    filename = f"sentiment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    file_path = os.path.join(output_dir, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return file_path




@mcp.tool()
async def send_email_with_attachment(to: str, subject: str, body: str, file_path: str) -> str:
    """发送带附件的电子邮件
    参数:
    to: 收件人邮箱
    subject: 邮件主题
    body: 邮件正文
    file_path: 附件文件的完整路径或相对路径
    """
    # 获取SMTP配置
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    # 确保SMTP配置完整
    if not all([smtp_server, smtp_port, smtp_user, smtp_password]):
        return "SMTP配置不完整，请检查.env文件"

    # 解析文件路径
    full_path = os.path.abspath(file_path)
    if not os.path.exists(full_path):
        return f"附件文件 {full_path} 不存在，请检查路径。"

    # 创建邮件消息
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to
    msg.set_content(body)

    # 添加附件
    try:
        with open(full_path, "rb") as f:
            file_data = f.read()
            file_name = os.path.basename(full_path)
            # 根据文件扩展名设置正确的MIME类型
            if file_name.endswith(".md"):
                maintype, subtype = "text", "markdown"
            elif file_name.endswith(".txt"):
                maintype, subtype = "text", "plain"
            elif file_name.endswith(".png"):
                maintype, subtype = "image", "png"
            elif file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
                maintype, subtype = "image", "jpeg"
            else:
                maintype, subtype = "application", "octet-stream"
            msg.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=file_name)
    except Exception as e:
        return f"读取附件文件失败：{str(e)}"

    # 发送邮件
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return f"邮件已成功发送到 {to}，主题：{subject}，附件：{file_name}"
    except smtplib.SMTPAuthenticationError:
        return "SMTP认证失败，请检查用户名和密码是否正确"
    except smtplib.SMTPConnectError:
        return f"无法连接到SMTP服务器 {smtp_server}:{smtp_port}"
    except Exception as e:
        return f"发送邮件失败：{str(e)}"
    

import asyncio

if __name__ == "__main__":
    print("Starting server...")
    try:
        # 直接运行异步函数
        async def run_server():
            print("Server is running asynchronously...")
            await mcp.run_stdio_async()
            print("Server completed successfully")

        asyncio.run(run_server())
        print("server.py started successfully")
    except Exception as e:
        print(f"Server failed to start: {str(e)}")
        import traceback
        traceback.print_exc()