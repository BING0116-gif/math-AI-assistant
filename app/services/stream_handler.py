"""
流式响应处理模块。

负责 SSE (Server-Sent Events) 格式的流式响应生成，
包括聊天流式、图片识别流式、多模态流式响应。
"""

import asyncio
import base64
import json
import logging
import os
import traceback
import time
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


async def with_sse_heartbeat(source, interval_seconds: float | None = None):
    """Keep an SSE connection alive while a producer is waiting on I/O.

    Heartbeats are SSE comments, so clients ignore them and replay buffers do
    not treat them as business events or advance Last-Event-ID.
    """
    try:
        from app.config.settings import settings

        if not settings.SSE_HEARTBEAT_ENABLED:
            async for item in source:
                yield item
            return
        interval = interval_seconds or settings.SSE_HEARTBEAT_SECONDS
    except Exception:
        interval = interval_seconds or 15.0

    iterator = source.__aiter__()
    pending = asyncio.create_task(iterator.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                try:
                    from app.observability import SSE_EVENTS
                    SSE_EVENTS.labels("heartbeat").inc()
                except Exception:
                    pass
                yield ": ping\n\n"
                continue
            try:
                yield pending.result()
            except StopAsyncIteration:
                return
            pending = asyncio.create_task(iterator.__anext__())
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        close = getattr(source, "aclose", None)
        if close is not None:
            await close()


async def stream_agent_response(
    agent,
    message: str,
    session_id: str,
    context_label: str = "聊天",
    user_id: str = None,
    tutor_mode: str = "step_by_step",
    tutor_context: dict | None = None,
    ai_run_id: str | None = None,
    stream_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """通用的 Agent 流式响应生成器。"""
    if not user_id:
        raise ValueError("user_id is required")
    logger.info(f"[SSE] 开始流式响应: session={session_id}, label={context_label}, user={user_id}")
    turn_started = time.time()
    first_content_at = None
    capability = "unknown"
    answer_parts: list[str] = []
    if stream_id:
        from app.services.stream_control import register_stream
        register_stream(stream_id)
    try:
        chunk_idx = 0
        started = time.perf_counter()
        user_cancelled = False
        async for chunk in agent.stream(message, session_id=session_id, user_id=user_id, tutor_mode=tutor_mode, tutor_context=tutor_context):
            if stream_id:
                from app.services.stream_control import is_cancelled
                if is_cancelled(stream_id):
                    user_cancelled = True
                    break
            if chunk:
                if isinstance(chunk, dict) and chunk.get("__agent_event__"):
                    payload = {key: value for key, value in chunk.items() if key != "__agent_event__"}
                    try:
                        from app.observability import SSE_EVENTS
                        SSE_EVENTS.labels("agent_step").inc()
                    except Exception:
                        pass
                    yield f"event: agent_step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    continue
                if not isinstance(chunk, str):
                    chunk = str(chunk)
                chunk_idx += 1
                answer_parts.append(chunk)
                if first_content_at is None:
                    first_content_at = time.perf_counter()
                try:
                    from app.observability import SSE_EVENTS
                    SSE_EVENTS.labels("content").inc()
                except Exception:
                    pass
                try:
                    yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"
                except (TypeError, ValueError) as json_error:
                    yield f"data: {json.dumps({'content': f'JSON序列化错误: {str(json_error)}', 'type': 'error'})}\n\n"

        if user_cancelled:
            # 用户主动停止（4.5）：已产出内容保留并照常落库；半截结果不进记忆/错题本。
            capability = str((getattr(agent, "_last_run_metadata", {}) or {}).get("capability") or "unknown")[:80]
            try:
                from app.observability import AGENT_RUNS
                AGENT_RUNS.labels(capability, "user_cancelled").inc()
            except Exception:
                pass
            logger.info(f"[SSE] 用户主动停止生成: session={session_id}")
            yield 'event: cancelled\ndata: {"type": "cancelled"}\n\n'
            yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
            if ai_run_id:
                from app.services.tutor_service import complete_ai_run
                await complete_ai_run(ai_run_id, status="user_cancelled", metadata=dict(getattr(agent, "_last_run_metadata", {}) or {}))
            return

        mode_denials = list((getattr(agent, "_last_run_metadata", {}) or {}).get("mode_tool_denials") or [])
        if mode_denials:
            payload = {
                "type": "mode_tool_denied",
                "message": "该模式下此操作不可用",
                "denials": mode_denials,
            }
            yield f"event: mode_guard\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        visualizations = list((getattr(agent, "_last_run_metadata", {}) or {}).get("visualizations") or [])
        for visualization in visualizations:
            yield (
                "event: visualization\ndata: "
                f"{json.dumps(visualization, ensure_ascii=False, allow_nan=False)}\n\n"
            )

        animations = list((getattr(agent, "_last_run_metadata", {}) or {}).get("animations") or [])
        for animation in animations:
            yield (
                "event: animation_job\ndata: "
                f"{json.dumps(animation, ensure_ascii=False, allow_nan=False)}\n\n"
            )

        # [T03] ask_student 结构化反问事件：本轮内工具创建了 pending 澄清时下发，
        # 前端据此渲染结构化问题卡片（选项按钮 + 自由输入）。此时跳过跟进推荐，
        # 避免在等待学生澄清回答时继续推荐练习。
        ask_student_payload = None
        try:
            from app.services.clarification_store import get_clarification_store
            record = await get_clarification_store().get_pending_created_after(
                user_id, session_id, turn_started
            )
            if record is not None:
                ask_student_payload = {"type": "ask_student", **record.to_payload()}
        except Exception as clarify_error:
            logger.warning(f"[SSE] ask_student 澄清事件检查失败（非阻塞）: {clarify_error}")

        if ask_student_payload:
            yield f"event: ask_student\ndata: {json.dumps(ask_student_payload, ensure_ascii=False)}\n\n"
            logger.info(f"[SSE] ask_student事件已推送 | session={session_id}")
            yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
            if ai_run_id:
                from app.services.tutor_service import complete_ai_run
                metadata = dict(getattr(agent, "_last_run_metadata", {}) or {})
                metadata["latency_ms"] = int((time.perf_counter() - started) * 1000)
                metadata["ask_student"] = True
                await complete_ai_run(ai_run_id, status="completed", metadata=metadata)
            return

        # [P0-03] 流式推送 follow_up 事件（推荐内容）
        follow_up = getattr(agent, '_follow_up_text', None)
        if follow_up:
            yield (
                f"event: follow_up\ndata: "
                f"{json.dumps({'type': 'recommendation', 'content': follow_up})}\n\n"
            )
            logger.info(f"[SSE] follow_up事件已推送 | session={session_id}")

        logger.info(f"[SSE] 流式响应完成: session={session_id}, total_chunks={chunk_idx}")
        metadata = dict(getattr(agent, "_last_run_metadata", {}) or {})
        capability = str(metadata.get("capability") or "unknown")[:80]
        run_status = str(getattr(agent, "_last_run_status", "") or "completed")
        if run_status not in {"completed", "timeout", "budget_exceeded", "degraded", "failed_l4"}:
            run_status = "completed"
        try:
            from app.observability import AGENT_RUNS, AGENT_LATENCY, AGENT_TTFT
            AGENT_RUNS.labels(capability, run_status).inc()
            AGENT_LATENCY.labels(capability).observe(time.perf_counter() - started)
            if first_content_at is not None:
                AGENT_TTFT.labels(capability).observe(first_content_at - started)
        except Exception:
            pass
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
        try:
            from app.observability import SSE_EVENTS
            SSE_EVENTS.labels("done").inc()
        except Exception:
            pass
        if ai_run_id:
            from app.services.tutor_service import complete_ai_run
            metadata = dict(getattr(agent, "_last_run_metadata", {}) or {})
            metadata["latency_ms"] = int((time.perf_counter() - started) * 1000)
            try:
                from app.services.answer_critic import AnswerCritic
                critic = await AnswerCritic().review(
                    run_id=ai_run_id,
                    question=message,
                    final_answer="".join(answer_parts),
                    requirements=(tutor_context or {}).get("requirements", []),
                )
                if critic is not None:
                    metadata.update({"critic_verdict": critic.verdict, "critic_issues": [issue.model_dump() for issue in critic.issues], "quality_sampled": True, "critic_model": critic.model})
                    # 5-C 可信度徽标:低基数 verdict + issue codes 下发,不含答案原文
                    yield (
                        "event: critic\ndata: "
                        + json.dumps(
                            {"verdict": critic.verdict, "issues": [issue.code for issue in critic.issues][:5]},
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
            except Exception:
                pass
            await complete_ai_run(ai_run_id, status=run_status, metadata=metadata)

    except Exception as e:
        try:
            from app.observability import AGENT_RUNS
            AGENT_RUNS.labels(capability, "failed").inc()
        except Exception:
            pass
        logger.error(f"[SSE] 流式{context_label}失败: {e}\n{traceback.format_exc()}")
        yield f"data: {json.dumps({'content': '服务器内部错误', 'type': 'error'})}\n\n"
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
        if ai_run_id:
            from app.services.tutor_service import complete_ai_run
            await complete_ai_run(ai_run_id, status="failed", error_code=type(e).__name__)

    except (GeneratorExit, asyncio.CancelledError):
        # 客户端断连/任务取消（4.5）：不触发记忆提炼与错题写入，run 记为断连；
        # DB 回写交给独立 task——生成器关闭期间不允许真正挂起等待。
        try:
            from app.observability import AGENT_RUNS
            AGENT_RUNS.labels(capability, "client_disconnected").inc()
        except Exception:
            pass
        if ai_run_id:
            from app.services.tutor_service import complete_ai_run
            asyncio.get_running_loop().create_task(complete_ai_run(ai_run_id, status="client_disconnected"))
        raise
    finally:
        if stream_id:
            from app.services.stream_control import unregister_stream
            unregister_stream(stream_id)


async def stream_recognize_response(
    agent,
    image_data: str,
    session_id: str,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """图片识别流式响应生成器。"""
    if not user_id:
        raise ValueError("user_id is required")
    try:
        if image_data.startswith("data:image/"):
            image_data = image_data.split(",")[1]

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_file.write(base64.b64decode(image_data))
            temp_file_path = temp_file.name

        try:
            start_msg = "**【正在识别图片内容...】**\n\n"
            yield f"data: {json.dumps({'content': start_msg, 'type': 'status'})}\n\n"

            async for chunk in agent.stream(
                temp_file_path, session_id=session_id, user_id=user_id
            ):
                if chunk:
                    if isinstance(chunk, dict) and chunk.get("__agent_event__"):
                        payload = {key: value for key, value in chunk.items() if key != "__agent_event__"}
                        yield f"event: agent_step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        continue
                    if not isinstance(chunk, str):
                        chunk = str(chunk)
                    yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"

            yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    except Exception as e:
        logger.error(f"图片识别流式处理失败: {e}\n{traceback.format_exc()}")
        yield f"data: {json.dumps({'content': '服务器内部错误', 'type': 'error'})}\n\n"
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"


async def stream_multimodal_response(
    agent,
    message: str,
    image_data: str,
    session_id: str,
    user_id: str = None,
    tutor_mode: str = "step_by_step",
    tutor_context: dict | None = None,
    ai_run_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """多模态（图片+文字）流式响应生成器。"""
    if not user_id:
        raise ValueError("user_id is required")
    try:
        if image_data:
            if image_data.startswith("data:image/"):
                image_data = image_data.split(",")[1]

            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_file.write(base64.b64decode(image_data))
                temp_file_path = temp_file.name

            try:
                start_msg = "**【正在识别图片内容...】**\n\n"
                yield f"data: {json.dumps({'content': start_msg, 'type': 'status'})}\n\n"

                started = time.perf_counter()
                async for chunk in agent.stream_multimodal(temp_file_path, message, session_id=session_id, user_id=user_id, tutor_mode=tutor_mode, tutor_context=tutor_context):
                    if chunk:
                        if isinstance(chunk, dict) and chunk.get("__agent_event__"):
                            payload = {key: value for key, value in chunk.items() if key != "__agent_event__"}
                            yield f"event: agent_step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                            continue
                        if not isinstance(chunk, str):
                            chunk = str(chunk)
                        yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"

                mode_denials = list((getattr(agent, "_last_run_metadata", {}) or {}).get("mode_tool_denials") or [])
                if mode_denials:
                    payload = {"type": "mode_tool_denied", "message": "该模式下此操作不可用", "denials": mode_denials}
                    yield f"event: mode_guard\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

                visualizations = list((getattr(agent, "_last_run_metadata", {}) or {}).get("visualizations") or [])
                for visualization in visualizations:
                    yield "event: visualization\ndata: " + json.dumps(visualization, ensure_ascii=False, allow_nan=False) + "\n\n"

                animations = list((getattr(agent, "_last_run_metadata", {}) or {}).get("animations") or [])
                for animation in animations:
                    yield "event: animation_job\ndata: " + json.dumps(animation, ensure_ascii=False, allow_nan=False) + "\n\n"

                yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
                if ai_run_id:
                    from app.services.tutor_service import complete_ai_run
                    metadata = dict(getattr(agent, "_last_run_metadata", {}) or {}); metadata["latency_ms"] = int((time.perf_counter() - started) * 1000)
                    run_status = str(getattr(agent, "_last_run_status", "") or "completed")
                    if run_status not in {"completed", "timeout", "budget_exceeded", "degraded", "failed_l4"}:
                        run_status = "completed"
                    await complete_ai_run(ai_run_id, status=run_status, metadata=metadata)
            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
        else:
            started = time.perf_counter()
            async for chunk in agent.stream(
                message, session_id=session_id, user_id=user_id, tutor_mode=tutor_mode, tutor_context=tutor_context
            ):
                if chunk:
                    if isinstance(chunk, dict) and chunk.get("__agent_event__"):
                        payload = {key: value for key, value in chunk.items() if key != "__agent_event__"}
                        yield f"event: agent_step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        continue
                    if not isinstance(chunk, str):
                        chunk = str(chunk)
                    yield f"data: {json.dumps({'content': chunk, 'type': 'content'})}\n\n"

            mode_denials = list((getattr(agent, "_last_run_metadata", {}) or {}).get("mode_tool_denials") or [])
            if mode_denials:
                payload = {"type": "mode_tool_denied", "message": "该模式下此操作不可用", "denials": mode_denials}
                yield f"event: mode_guard\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            visualizations = list((getattr(agent, "_last_run_metadata", {}) or {}).get("visualizations") or [])
            for visualization in visualizations:
                yield "event: visualization\ndata: " + json.dumps(visualization, ensure_ascii=False, allow_nan=False) + "\n\n"

            animations = list((getattr(agent, "_last_run_metadata", {}) or {}).get("animations") or [])
            for animation in animations:
                yield "event: animation_job\ndata: " + json.dumps(animation, ensure_ascii=False, allow_nan=False) + "\n\n"

            yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
            if ai_run_id:
                from app.services.tutor_service import complete_ai_run
                metadata = dict(getattr(agent, "_last_run_metadata", {}) or {})
                metadata["latency_ms"] = int((time.perf_counter() - started) * 1000)
                run_status = str(getattr(agent, "_last_run_status", "") or "completed")
                if run_status not in {"completed", "timeout", "budget_exceeded", "degraded", "failed_l4"}:
                    run_status = "completed"
                await complete_ai_run(ai_run_id, status=run_status, metadata=metadata)

    except (GeneratorExit, asyncio.CancelledError):
        # 断连/取消（4.5）：半截多模态结果不落库为完成，run 记为断连。
        try:
            from app.observability import AGENT_RUNS
            AGENT_RUNS.labels("multimodal", "client_disconnected").inc()
        except Exception:
            pass
        if ai_run_id:
            from app.services.tutor_service import complete_ai_run
            asyncio.get_running_loop().create_task(complete_ai_run(ai_run_id, status="client_disconnected"))
        raise

    except Exception as e:
        logger.error(f"多模态流式处理失败: {e}\n{traceback.format_exc()}")
        yield f"data: {json.dumps({'content': '服务器内部错误', 'type': 'error'})}\n\n"
        yield f"data: {json.dumps({'content': '', 'type': 'done'})}\n\n"
        if ai_run_id:
            from app.services.tutor_service import complete_ai_run
            await complete_ai_run(ai_run_id, status="failed", error_code=type(e).__name__)
