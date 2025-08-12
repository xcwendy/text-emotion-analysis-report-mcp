import os
import re
import sys
from openai import OpenAI
from mcp.client.stdio import stdio_client
from mcp import ClientSession,StdioServerParameters
from contextlib import AsyncExitStack
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import json
import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("client.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("client")

load_dotenv()

class MCPClient:

    def __init__(self):
        self.exit_stack = AsyncExitStack()
        #从环境变量中获取API密钥和基础URL
        self.api_key = os.getenv("QWEN_API_KEY")
        self.base_url = os.getenv("BASE_URL")
        self.model = os.getenv("MODEL")
        if not self.api_key:
            raise ValueError("QWEN_API_KEY environment variable is not set.")
        # 确保正确配置会话超时参数
        self.client = OpenAI(
                    base_url = self.base_url,
                    api_key = self.api_key,
                    timeout=60)  # 增加超时值到60秒
        self.session: Optional[ClientSession] = None
        
        
    async def connect_to_server(self,server_script_path:str):
        #判断脚本类型
        is_py = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_py or is_js):
            raise ValueError("Server script must be a Python (.py) or JavaScript (.js) file.")
        
        command = "python" if is_py else "node"
        logger.info(f"Using command: {command} to start server script: {server_script_path}")

        #构造命令，传递环境变量
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        server_params = StdioServerParameters(
            command=command, args=[server_script_path],
            env=env
        )
        logger.info(f"Server parameters: {server_params}")
        #print(f"Trying to start server with command: {server_params.command}")
        #print(f"Server script absolute path: {server_script_path}")
        
        #连接到MCP服务器
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params))
        #拆包通信，读取服务端返回数据
        self.stdio,self.write = stdio_transport
        

        #创建MCP客户端会话对象
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write, self.client)
        )
        
        # 尝试设置会话超时（如果支持）
        if hasattr(self.session, '_session_read_timeout_seconds'):
            import datetime
            self.session._session_read_timeout_seconds = datetime.timedelta(seconds=60)  # 增加超时值到60秒

        #初始化会话
        await self.session.initialize()

        #获取工具列表并打印
        response = await self.session.list_tools()
        tools = response.tools
        print("Connect to the server successfully. Available tools:", [tool.name for tool in tools])

    async def process_query(self,query:str) -> str:
        if not self.session:
            raise RuntimeError("Client session is not initialized. Please connect to the server first.")
        
        #发送查询到MCP服务器
        messages = [{"role": "user", "content": query}]
        response = await self.session.list_tools()
        
        #处理工具列表
        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                } 
            } for tool in response.tools
        ]

        #提取问题关键词
        keyword_match = re.search(r"(关于|分析|查询|搜索|查看)([^的、s. 。 、 ? \n]+)", query)
        keyword = keyword_match.group(2) if keyword_match else "分析对象"
        safe_keyword = re.sub(r"[^\w\s]", "", keyword)  # 移除特殊字符
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_filename = f"sentiment_{safe_keyword}_{timestamp}.md"
        md_path = os.path.join("./sentiment_reports", md_filename)

        #更新查询，将文件名添加到原始查询中。调用plan_tool_usage获取工具使用计划
        query = query.strip() + f"[md_filename={md_filename}][md_path={md_path}]"
        messages = [{"role": "user", "content": query}]

        tool_plan = await self.plan_tool_usage(query, available_tools)
        tool_outputs = {}
        messages = [{"role": "user", "content": query}]

        #执行工具调用
        for tool in tool_plan:
            tool_name = tool["name"]
            tool_args = tool["arguments"]

            for key,value in tool_args.items():
                if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                    # 替换占位符
                    placeholder = value.strip("{} ")
                    tool_args[key] = tool_outputs.get(placeholder, value)
            if tool_name == "analyze_sentiment" and "filename" not in tool_args:
                tool_args["filename"] = md_filename
            if tool_name == "send_email_with_attachment" and "attachment_path" not in tool_args:
                tool_args["attachment_path"] = md_path

            result = await self.session.call_tool(
                tool_name=tool_name,
                tool_args=tool_args
            )

            tool_outputs[tool_name] = result.content[0].text
            messages.append({
                "role": "tool",
                "tool_call_id": tool_name,
                "content": f"Tool {tool_name} executed with result: {result.content[0].text}"
            })

        #生成最终回答
        final_response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        final_output = final_response.choices[0].message.content


        #文本清理为合法文件名
        def clean_filename(text:str) ->str:
            text = text.strip()
            text = re.sub(r'[\\/:*?"<>|]', '', text)
            return text[:50]  # 限制长度为50个字符
        
        #用清理函数处理用户输入，生成文件命名前缀，并添加时间戳设置输出目录
        save_filename = clean_filename(query)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{save_filename}_{timestamp}.txt"
        output_dir = "./llm_outputs"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)

        #保存输出到文件
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"用户提问：{query}\n")
            f.write(f"模型回复：\n{final_output}\n")
        print(f"Output saved to {output_path}")

        return final_output
    
    async def chat_loop(self):
        print("欢迎使用MCP客户端！输入'退出'或'quit'结束对话。")

        while True:
            user_input = input("请输入您的问题：")
            if user_input.lower() in ["退出", "quit"]:
                print("感谢使用MCP客户端，再见！")
                break
            try:
                response = await self.process_query(user_input)
                print(f"模型回复：{response}")
            except Exception as e:
                print(f"发生错误：{e}")

    async def plan_tool_usage(self, query: str, available_tools: list) -> list:
        if not self.session:
            raise RuntimeError("Client session is not initialized. Please connect to the server first.")
        
        #调用MCP服务器的plan_tool_usage方法
        print("\n 提交给大模型的工具定义：")
        print(json.dumps(available_tools, indent=2, ensure_ascii=False))
        tool_list_text = "\n".join(
            [f"{tool['function']['name']}: {tool['function']['description']}" for tool in available_tools]
        )
        system_prompt = {
            "role": "system",
            "content": ("你是一个智能助手，用户会给出一句请求。以下是可用的工具列表（请严格使用工具名称）：\n"
                        f"{tool_list_text}\n"
                        "请根据用户的查询计划使用这些工具。"
                        "如果多个工具需要串联，后续步骤中可以使用{{上一步工具名}}占位。\n"
                        "返回格式：JSON数组，每个对象包含name和arguments字段"
                        )
        }
        
        #构造消息列表，将系统提示和用户query一起作为消息输入
        messages = [system_prompt, {"role": "user", "content": query}]
        # 为工具使用计划调用添加显式超时设置
        logger.info("开始计划工具使用，设置超时60秒")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=available_tools,
            tool_choice="none",  # 不直接调用工具，先获取计划
            timeout=60  # 显式设置超时为60秒
        )
        logger.info("工具使用计划获取成功")

        #提取模型返回的json
        content = response.choices[0].message.content.strip()
        match = re.search(r"'''(?:json)?\\s*([\s\S]+?)\\s*'''", content)
        if match:
            json_str = match.group(1)
        else:
            json_str = content

        #解析调用计划
        try:
            tool_plan = json.loads(json_str)
            logger.info(f"成功解析工具计划: {tool_plan}")
            return tool_plan if isinstance(tool_plan, list) else []
        except Exception as e:
            logger.error(f"解析工具计划失败: {e}")
            print(f"failed to parse tool plan: {e}")
            return []
        
    async def cleanup(self):
        await self.exit_stack.aclose()


async def main():
    client = None
    try:
        logger.info("Starting client...")

        # 检查环境变量
        required_vars = ["QWEN_API_KEY", "BASE_URL", "MODEL"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            logger.error(f"缺少必要的环境变量: {', '.join(missing_vars)}")
            print(f"错误: 缺少必要的环境变量: {', '.join(missing_vars)}")
            return

        client = MCPClient()
        server_script_path = os.path.join("server.py") # 替换为实际的服务器脚本路径
        logger.info("connect to server 即将执行")
        try:
            await client.connect_to_server(server_script_path)
            await client.chat_loop()
        except Exception as e:
            logger.error(f"发生错误：{e}", exc_info=True)
            print(f"发生错误：{e}")
            raise
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
        print(f"发生意外错误：{e}")
    finally:
        if client:
            await client.cleanup()

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"致命错误：{e}", exc_info=True)
        print(f"致命错误：{e}")
        import traceback
        traceback.print_exc()




