from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class PluginInterface(ABC):
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def execute(self, input_data: Any) -> Any:
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, str]:
        return {
            "name": "",
            "version": "",
            "author": "",
            "description": "",
            "dependencies": [],
        }

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy", "details": {}}

    async def shutdown(self) -> None:
        pass


class PluginManager:
    def __init__(self):
        self._plugins: Dict[str, PluginInterface] = {}

    def register(self, name: str, plugin: PluginInterface) -> None:
        if name in self._plugins:
            raise ValueError(f"插件 '{name}' 已注册")
        self._plugins[name] = plugin
        logger.info(f"插件已注册: {name}")

    def unregister(self, name: str) -> None:
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"插件已注销: {name}")

    def get(self, name: str) -> Optional[PluginInterface]:
        return self._plugins.get(name)

    def list_plugins(self) -> List[Dict[str, str]]:
        return [
            {"name": name, **plugin.get_info()}
            for name, plugin in self._plugins.items()
        ]

    async def initialize_all(self, configs: Dict[str, Dict] = None) -> bool:
        configs = configs or {}
        all_ok = True
        for name, plugin in self._plugins.items():
            config = configs.get(name, {})
            try:
                ok = await plugin.initialize(config)
                if not ok:
                    logger.warning(f"插件初始化失败: {name}")
                    all_ok = False
            except Exception as e:
                logger.error(f"插件初始化异常: {name}, {e}")
                all_ok = False
        return all_ok

    async def shutdown_all(self) -> None:
        for name, plugin in self._plugins.items():
            try:
                await plugin.shutdown()
            except Exception as e:
                logger.error(f"插件关闭异常: {name}, {e}")

    async def health_check_all(self) -> Dict[str, Any]:
        results = {}
        all_healthy = True
        for name, plugin in self._plugins.items():
            try:
                check = await plugin.health_check()
                results[name] = check
                if check.get("status") != "healthy":
                    all_healthy = False
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                all_healthy = False

        return {
            "overall": "healthy" if all_healthy else "degraded",
            "plugins": results,
        }


_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager