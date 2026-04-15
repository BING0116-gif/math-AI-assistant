from typing import Dict, Any, Optional, Tuple, Union
from sympy import symbols, integrate, parse_expr
from config.prompts import SYSTEM_PROMPT
# 导入LangChain组件
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.callbacks import StreamingStdOutCallbackHandler


class SimpleAgent:
    def __init__(self, tools: Dict[str, Any], api_key: str, vision_tool=None):
        self.tools = tools  # Tool 注册表
        
        self.api_key = api_key  # 千问API密钥
        self.vision_tool = vision_tool  # 多模态图片识别工具

        # 初始化LangChain组件
        self.chain = None
        self._default_session_id = "default"
        self._session_histories: Dict[str, InMemoryChatMessageHistory] = {}

        # 初始化LangChain
        self._initialize_langchain()
    
    def _initialize_langchain(self):
        """初始化LangChain组件"""
        
        assert self.api_key, "千问API密钥必须提供"
        
        # 创建ChatOpenAI实例，支持流式输出
        self.llm = ChatOpenAI(
            model="qwen-max",
            temperature=0,
            api_key=self.api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            streaming=True
        )
        
        # 创建提示词模板（history 由 RunnableWithMessageHistory 注入）
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
        ])
        
        # 创建输出解析器
        output_parser = StrOutputParser()
        
        # 基础链 + 多轮对话包装
        base_chain = prompt | self.llm | output_parser
        self.chain = RunnableWithMessageHistory(
            base_chain,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="history",
        )
        
        print("LangChain初始化成功（已启用多轮对话）")

    def _get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        if session_id not in self._session_histories:
            self._session_histories[session_id] = InMemoryChatMessageHistory()
        return self._session_histories[session_id]

    def process_input(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        """处理用户输入（同一 session_id 下保留多轮上下文）。

        stream=True 时通过 LangChain 回调把模型输出逐 token 写到标准输出；
        invoke 仍会返回完整字符串（便于 Sympy 等后处理）。
        """
        sid = session_id if session_id is not None else self._default_session_id
        config: Dict[str, Any] = {"configurable": {"session_id": sid}}
        if stream:
            config["callbacks"] = [StreamingStdOutCallbackHandler()]

        # 检查是否是图片输入（文件路径）
        if self._is_image_input(user_input):
            return self._process_image_path(user_input, sid, config, stream)

        full_response = self.chain.invoke({"input": user_input}, config=config)
        if stream:
            print()

        # 如果是积分问题，添加Sympy验证
        recognition_result = self.recognizer.recognize(user_input)
        if recognition_result.get("type") == "integration" or "积分" in user_input:
            verification_result = self._verify_with_sympy({
                "text": user_input,
                "expression": recognition_result.get("expression", ""),
                "variable": recognition_result.get("variable", "x")
            }, full_response)
            merged = f"{full_response}{verification_result}"
            if stream:
                print(verification_result, end="", flush=True)
                print()
            return merged
        return full_response

    def process_image_multimodal(
        self,
        image_source: Union[str, Tuple[str, str]],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        用 Qwen-VL 端到端识别图片，返回结构化结果。
        image_source: 文件路径 或 (mime, base64) tuple
        """
        if not self.vision_tool:
            return {
                "success": False,
                "llm_description": "",
                "raw_response": "",
                "error": "VisionTool 未注册",
                "model_used": "",
            }
        return self.vision_tool.recognize(image_source)

    def _is_image_input(self, user_input: str) -> bool:
        """检查用户输入是否是图片路径"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']
        user_input_lower = user_input.lower().strip()
        return any(user_input_lower.endswith(ext) for ext in image_extensions)

    def _process_image_path(self, image_path: str, session_id: str, config: Dict[str, Any], stream: bool) -> str:
        """处理图片路径输入（使用VisionTool进行多模态识别）"""
        if not self.vision_tool:
            error_msg = "VisionTool未注册，无法处理图片"
            if stream:
                print(error_msg, end="", flush=True)
                print()
            return error_msg
        
        # 使用VisionTool进行多模态识别
        vl_result = self.vision_tool.recognize(image_path)
        if not vl_result["success"]:
            error_msg = f"图片识别失败：{vl_result.get('error', '未知错误')}"
            if stream:
                print(error_msg, end="", flush=True)
                print()
            return error_msg

        recognized_text = vl_result["llm_description"]
        display_msg = f"【图片识别结果】\n{recognized_text}\n\n"
        if stream:
            print(display_msg, end="", flush=True)

        full_response = self.chain.invoke({"input": recognized_text}, config=config)

        return f"{display_msg}{full_response}"
    
    def clear_history(self, session_id: Optional[str] = None) -> None:
        """清空指定会话的对话记忆；默认清空当前默认会话。"""
        sid = session_id if session_id is not None else self._default_session_id
        hist = self._session_histories.get(sid)
        if hist is not None:
            hist.clear()
    
    def _verify_with_sympy(self, problem: Dict[str, str], qwen_answer: str) -> str:
        """使用sympy验证千问API的答案"""
        try:
            text = problem.get("text", "")
            expression_str = problem.get("expression", "")
            variable = problem.get("variable", "x")
            
            if not expression_str:
                recognition_result = self.recognizer.recognize(text)
                expression_str = recognition_result.get("expression", "")
                variable = recognition_result.get("variable", "x")
            
            if not expression_str:
                return "无法提取数学表达式进行验证。"
            
            x = symbols(variable)
            expression = parse_expr(expression_str)
            correct_answer = integrate(expression, x)
            
            return f"\n\n【Sympy验证】\n原函数：{expression}\n积分结果：{correct_answer}"
            
        except Exception as e:
            return f"\n\n【Sympy验证】\n验证过程出错：{str(e)}"
    
    def solve_problem(self, problem: Dict[str, str]) -> str:
        math_solver = self.tools.get("math_solver")
        return math_solver.solve(problem)
