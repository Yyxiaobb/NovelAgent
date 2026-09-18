import os
from openai import OpenAI
from typing import List, Dict
from dotenv import load_dotenv
load_dotenv()

class NovelAgent:
    def __init__(self, model: str = None, api_key: str = None, base_url: str = None, provider: str = None, timeout: int = None, build_target: str = None):
        self.model = model or os.getenv('MODEL')
        api_key = api_key or os.getenv('API_KEY')
        base_url = base_url or os.getenv('BASE_URL')
        self.provider = provider or os.getenv('PROVIDER')
        timeout = timeout or int(os.getenv('TIMEOUT',60))
        self.build_target = build_target

        if not all([self.model, api_key, base_url]):
            raise ValueError("模型、API密钥和服务地址必须被提供或在.env文件中定义。")

        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def think(self, messages: List[Dict[str, str]], temperature: float = 0, ) -> str:
        print(f"🧠 正在生成{self.build_target}...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=True
            )

            # 处理流式响应
            print(f"✅ 成功生成:{self.build_target}")
            collected_content = []
            for chunk in response:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
                collected_content.append(content)
            print() # 在流式输出结束后换行
            return "".join(collected_content)

        except Exception as e:
            print(f"生成{self.build_target}时发生错误: {e}")
            return None


