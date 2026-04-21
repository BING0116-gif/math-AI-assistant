from tools.math_solver import MathSolverTool
from tools.vision_tool import VisionTool
from agent_core.agent import SimpleAgent
from error_book import ErrorBookManager, ErrorItem
from data_processing.validators import ErrorBookValidator
from data_processing.formatters import ErrorBookFormatter
import os
import base64
import json
from fastapi import FastAPI, HTTPException
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
                # 检查chunk是否为有效的JSON
                try:
                    json.dumps({'content': chunk})
                except (TypeError, ValueError) as json_error:
                    yield f"data: {json.dumps({'content': f'JSON序列化错误: {str(json_error)}'})}\n\n"
                    return
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        # 发送结束标志
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'content': f'错误: {str(e)}'})}\n\n"

# 流式生成器函数（图片识别）
async def stream_recognize_response(image_data, session_id):
    """生成器函数，逐token返回图片识别响应"""
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
        
        # 调用agent的stream_process方法处理图片
        async for chunk in agent.stream_process(temp_file_path, session_id=session_id):
            if chunk:
                # 确保chunk是字符串
                if not isinstance(chunk, str):
                    chunk = str(chunk)
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        
        # 删除临时文件
        os.unlink(temp_file_path)
        
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

# API端点：图片识别（流式响应）
@app.post('/api/recognize')
async def recognize(request: RecognizeRequest):
    image_data = request.image
    session_id = request.session_id
    
    if not image_data:
        raise HTTPException(status_code=400, detail="请提供图片数据")
    
    return StreamingResponse(
        stream_recognize_response(image_data, session_id),
        media_type="text/event-stream"
    )

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
        # Step 1: 数据校验 - 验证字段完整性和格式
        raw_data = request.dict()
        is_valid, validation_errors = ErrorBookValidator.validate(raw_data)
        
        if not is_valid:
            raise HTTPException(
                status_code=400, 
                detail=f"数据验证失败: {'; '.join(validation_errors)}"
            )
        
        # Step 2: 数据格式化 - 智能提取和标准化处理
        formatted_data = ErrorBookFormatter.format(raw_data)
        
        # Step 3: 创建错题对象并保存
        error_item = ErrorItem(
            id=formatted_data.get('id', ''),
            question=formatted_data.get('question', ''),
            question_type=formatted_data.get('question_type', 'text'),
            image_path=formatted_data.get('image_path'),
            error_reason=formatted_data.get('error_reason', ''),
            categories=formatted_data.get('categories', []),
            original_answer=formatted_data.get('original_answer', ''),
            correct_answer=formatted_data.get('correct_answer', ''),
            notes=formatted_data.get('notes', ''),
            added_at=formatted_data.get('added_at', ''),
            mastery_level=formatted_data.get('mastery_level', 3),
            is_mastered=formatted_data.get('is_mastered', False)
        )
        
        error_id = error_book_manager.add(error_item)
        
        # Step 4: 返回完整的格式化数据（包含处理后的新字段）
        return {
            "id": error_id,
            "status": "success",
            "message": "错题添加成功",
            "data": {
                **error_item.to_dict(),
                "display_question": formatted_data.get('display_question', ''),
                "recognized_text": formatted_data.get('recognized_text', ''),
                "answer_preview": formatted_data.get('answer_preview', ''),
                "has_image": formatted_data.get('has_image', False),
                "categories": formatted_data.get('categories', [])
            }
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

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
