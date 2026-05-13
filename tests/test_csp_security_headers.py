import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app


def test_csp_header_in_debug_mode():
    """验证DEBUG模式下CSP头始终存在"""
    with patch('main.settings') as mock_settings:
        mock_settings.DEBUG = True
        
        client = TestClient(app)
        response = client.get("/")
        
        assert "Content-Security-Policy" in response.headers, \
            "❌ 失败: DEBUG模式下缺少CSP头"
        
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp, \
            "❌ 失败: CSP缺少基础default-src策略"
        assert "frame-ancestors 'self'" in csp, \
            "✅ 通过: DEBUG模式使用宽松的frame-ancestors策略"
        assert "'unsafe-eval'" in csp, \
            "✅ 通过: DEBUG模式允许unsafe-eval（便于调试）"


def test_csp_header_in_production_mode():
    """验证生产模式下CSP头更严格"""
    with patch('main.settings') as mock_settings:
        mock_settings.DEBUG = False
        
        client = TestClient(app)
        response = client.get("/")
        
        assert "Content-Security-Policy" in response.headers, \
            "❌ 失败: 生产模式下缺少CSP头"
        
        csp = response.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp, \
            "✅ 通过: 生产模式严格禁止frame嵌入"
        assert "'unsafe-eval'" not in csp, \
            "✅ 通过: 生产模式禁止unsafe-eval（增强XSS防护）"


def test_permissions_policy_always_set():
    """验证Permissions-Policy始终设置"""
    for debug_mode in [True, False]:
        with patch('main.settings') as mock_settings:
            mock_settings.DEBUG = debug_mode
            
            client = TestClient(app)
            response = client.get("/")
            
            assert "Permissions-Policy" in response.headers, \
                f"❌ 失败: DEBUG={debug_mode}时缺少Permissions-Policy"
            
            pp = response.headers["Permissions-Policy"]
            assert "camera=()" in pp, \
                f"✅ 通过: DEBUG={debug_mode}时禁用摄像头"
            assert "microphone=()" in pp, \
                f"✅ 通过: DEBUG={debug_mode}时禁用麦克风"
            assert "geolocation=()" in pp, \
                f"✅ 通过: DEBUG={debug_mode}时禁用地理位置"


def test_other_security_headers_always_present():
    """验证其他安全头始终存在"""
    with patch('main.settings') as mock_settings:
        mock_settings.DEBUG = True
        
        client = TestClient(app)
        response = client.get("/")
        
        required_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }
        
        for header, expected_value in required_headers.items():
            assert header in response.headers, \
                f"❌ 失败: 缺少{header}头"
            assert response.headers[header] == expected_value, \
                f"❌ 失败: {header}值不正确"


def test_csp_connect_src_debug_vs_production():
    """验证DEBUG和生产模式的connect-src差异"""
    with patch('main.settings') as mock_settings:
        mock_settings.DEBUG = True
        client = TestClient(app)
        response = client.get("/")
        debug_csp = response.headers["Content-Security-Policy"]
        
        assert "http://localhost:" in debug_csp or "https://localhost:" in debug_csp, \
            "✅ 通过: DEBUG模式允许localhost HTTP连接（便于开发调试）"
    
    with patch('main.settings') as mock_settings:
        mock_settings.DEBUG = False
        client = TestClient(app)
        response = client.get("/")
        prod_csp = response.headers["Content-Security-Policy"]
        
        assert "http://localhost:" not in prod_csp, \
            "✅ 通过: 生产模式禁止HTTP明文连接"
        assert "wss://" in prod_csp, \
            "✅ 通过: 生产模式仅允许WSS安全WebSocket连接"


if __name__ == "__main__":
    print("🧪 开始运行CSP安全头测试...\n")
    pytest.main([__file__, "-v", "--tb=short"])
