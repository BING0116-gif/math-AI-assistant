from tools.math_solver import MathSolverTool
from tools.vision_tool import VisionTool
from agent_core.agent import SimpleAgent
from error_book import ErrorBookManager, ErrorItem
import os
import base64
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse,StreamingResponse
from pydantic import BaseModel

app = FastAPI()

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic模型
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class RecognizeRequest(BaseModel):
    image: str
    session_id: str = "default"

class ErrorItemRequest(BaseModel):
    id: str = ""
    question: str
    question_type: str = "text"
    image_path: str | None = None
    error_reason: str = ""
    categories: list[str] = []
    original_answer: str = ""
    correct_answer: str = ""
    notes: str = ""
    added_at: str = ""
    mastery_level: int = 3
    is_mastered: bool = False

class ErrorUpdateRequest(BaseModel):
    question: str | None = None
    question_type: str | None = None
    image_path: str | None = None
    error_reason: str | None = None
    categories: list[str] | None = None
    original_answer: str | None = None
    correct_answer: str | None = None
    notes: str | None = None
    added_at: str | None = None
    mastery_level: int | None = None
    is_mastered: bool | None = None

def load_env_file(file_path=".env"):
    """手动加载.env文件"""
    api_key = None
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key == "DASHSCOPE_API_KEY":
                        api_key = value
                        break
    return api_key

# 从.env文件读取API密钥
api_key = load_env_file(".env")

# 初始化 Tools
math_solver = MathSolverTool()
vision_tool = VisionTool(api_key=api_key)
# 初始化 Agent （注册工具）
agent = SimpleAgent(tools={"math_solver": math_solver}, api_key=api_key, vision_tool=vision_tool)
# 初始化错题本管理器
error_book_manager = ErrorBookManager()

# 流式生成器函数
async def stream_chat_response(message, session_id):
    """生成器函数，逐token返回响应"""
    try:
        # 调用agent的stream_process方法
        async for chunk in agent.stream_process(message, session_id=session_id):
            if chunk:
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        # 发送结束标志
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'content': f'错误: {str(e)}'})}\n\n"
        yield "data: [DONE]\n\n"

# API端点：对话（流式响应）
@app.post('/api/chat')
async def chat(request: ChatRequest):
    user_input = request.message
    session_id = request.session_id
    
    if not user_input:
        raise HTTPException(status_code=400, detail="请输入消息")
    
    return StreamingResponse(
        stream_chat_response(user_input, session_id),
        media_type="text/event-stream"
    )

# API端点：图片识别
@app.post('/api/recognize')
def recognize(request: RecognizeRequest):
    image_data = request.image
    session_id = request.session_id
    
    if not image_data:
        raise HTTPException(status_code=400, detail="请提供图片数据")
    
    try:
        # 处理base64图片数据
        if image_data.startswith('data:image/'):
            # 移除data URL前缀
            image_data = image_data.split(',')[1]
        
        # 保存图片到临时文件
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_file.write(base64.b64decode(image_data))
            temp_file_path = temp_file.name
        
        # 处理图片
        response = agent.process_input(temp_file_path, session_id=session_id, stream=False)
        
        # 删除临时文件
        os.unlink(temp_file_path)
        
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# API端点：错题本 - 获取所有错题
@app.get('/api/error-book')
def get_error_book():
    try:
        errors = error_book_manager.get_all()
        return [error.to_dict() for error in errors]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# API端点：错题本 - 添加错题
@app.post('/api/error-book')
def add_error(request: ErrorItemRequest):
    try:
        error_item = ErrorItem(
            id=request.id,
            question=request.question,
            question_type=request.question_type,
            image_path=request.image_path,
            error_reason=request.error_reason,
            categories=request.categories,
            original_answer=request.original_answer,
            correct_answer=request.correct_answer,
            notes=request.notes,
            added_at=request.added_at,
            mastery_level=request.mastery_level,
            is_mastered=request.is_mastered
        )
        
        error_id = error_book_manager.add(error_item)
        return {"id": error_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# API端点：错题本 - 更新错题
@app.put('/api/error-book/{error_id}')
def update_error(error_id: str, request: ErrorUpdateRequest):
    try:
        # 构建更新数据
        update_data = {}
        if request.question is not None:
            update_data['question'] = request.question
        if request.question_type is not None:
            update_data['question_type'] = request.question_type
        if request.image_path is not None:
            update_data['image_path'] = request.image_path
        if request.error_reason is not None:
            update_data['error_reason'] = request.error_reason
        if request.categories is not None:
            update_data['categories'] = request.categories
        if request.original_answer is not None:
            update_data['original_answer'] = request.original_answer
        if request.correct_answer is not None:
            update_data['correct_answer'] = request.correct_answer
        if request.notes is not None:
            update_data['notes'] = request.notes
        if request.added_at is not None:
            update_data['added_at'] = request.added_at
        if request.mastery_level is not None:
            update_data['mastery_level'] = request.mastery_level
        if request.is_mastered is not None:
            update_data['is_mastered'] = request.is_mastered
        
        success = error_book_manager.update(error_id, **update_data)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# API端点：错题本 - 删除错题
@app.delete('/api/error-book/{error_id}')
def delete_error(error_id: str):
    try:
        success = error_book_manager.remove(error_id)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 静态文件服务 (需要在挂载静态目录之后定义)
@app.get('/')
def index():
    return FileResponse('static/index.html')

@app.get('/error_book')
def error_book():
    return FileResponse('static/error_book.html')

if __name__ == "__main__":
    # 确保static目录存在
    if not os.path.exists('static'):
        os.makedirs('static')

    # 复制HTML文件到static目录
    import shutil
    if os.path.exists('ui_components/index.html'):
        shutil.copy('ui_components/index.html', 'static/')
    if os.path.exists('ui_components/error_book.html'):
        shutil.copy('ui_components/error_book.html', 'static/')

    print("\n服务器启动中...")
    print("访问地址: http://localhost:8000")
    print("API文档: http://localhost:8000/docs")

    # 使用uvicorn启动服务器
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
