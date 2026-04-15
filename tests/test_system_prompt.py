from langchain_core.prompts import ChatPromptTemplate
from config.prompts import SYSTEM_PROMPT

# 测试实际的系统提示词
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{input}"),
])

print("系统提示词模板测试成功")

# 打印系统提示词的长度和前100个字符
print(f"系统提示词长度: {len(SYSTEM_PROMPT)}")
print(f"系统提示词前100字符: {SYSTEM_PROMPT[:100]}...")
