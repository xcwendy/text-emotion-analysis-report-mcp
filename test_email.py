import asyncio
import os
from server import send_email_with_attachment

async def test_send_email():
    # 测试参数
    to_email = "wendy_xue_cw@163.com"
    subject = "测试带附件的邮件发送"
    body = "这是一封测试邮件，包含附件。"
    
    # 确保测试文件存在
    test_file_path = os.path.join("./llm_outputs", "整理网友对小米su7的看法，生成情感分析文件，生成一个饼图，包含“正面”、“中性”、“负面”三类情感_20250804_155850.txt")
    
    if not os.path.exists(test_file_path):
        print(f"测试文件不存在: {test_file_path}")
        return
    
    print(f"开始发送邮件到 {to_email}，附件: {test_file_path}")
    result = await send_email_with_attachment(
        to=to_email,
        subject=subject,
        body=body,
        file_path=test_file_path
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(test_send_email())