import requests
import json

def run_security_tests():
    print('=== Security Tests ===')
    print()

    print('1. Testing login endpoint...')
    resp = requests.post('http://127.0.0.1:8000/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
    print(f'   Status: {resp.status_code}')
    if resp.status_code == 200:
        print('   Login successful')
        data = resp.json()
        token = data['data']['access_token']
        refresh_token = data['data']['refresh_token']
    else:
        print(f'   Login failed: {resp.text}')
        return

    print()
    print('2. Testing register endpoint...')
    resp = requests.post('http://127.0.0.1:8000/api/auth/register', json={'username': 'testuser3', 'password': 'test123456'})
    print(f'   Status: {resp.status_code}')
    if resp.status_code == 200 or resp.status_code == 409:
        print('   Register endpoint works')
    else:
        print(f'   Register failed: {resp.text}')

    print()
    print('3. Testing unauthorized chat access...')
    resp = requests.post('http://127.0.0.1:8000/api/chat', json={'message': 'hello', 'session_id': 'test'})
    print(f'   Status: {resp.status_code}')
    if resp.status_code == 401:
        print('   Unauthorized request correctly denied')
    else:
        print('   WARNING: Unauthorized request not denied')

    print()
    print('4. Testing authorized chat access with token...')
    resp = requests.post('http://127.0.0.1:8000/api/chat', json={'message': 'hello', 'session_id': 'test'}, headers={'Authorization': 'Bearer ' + token})
    print(f'   Status: {resp.status_code}')
    if resp.status_code == 200:
        print('   Token authentication works')
    else:
        print(f'   Authentication failed: {resp.text}')

    print()
    print('5. Testing XSS attack detection...')
    xss_payload = '<script>alert(1)</script>'
    resp = requests.post('http://127.0.0.1:8000/api/auth/login', json={'username': xss_payload, 'password': 'test'})
    print(f'   Status: {resp.status_code}')
    if resp.status_code == 400:
        print('   XSS attack detected')
    else:
        print('   WARNING: XSS attack not detected')

    print()
    print('6. Testing SQL injection detection...')
    sql_payload = "admin' OR 1=1--"
    resp = requests.post('http://127.0.0.1:8000/api/auth/login', json={'username': sql_payload, 'password': 'test'})
    print(f'   Status: {resp.status_code}')
    if resp.status_code == 400:
        print('   SQL injection detected')
    else:
        print('   WARNING: SQL injection not detected')

    print()
    print('7. Testing CORS headers...')
    resp = requests.options('http://127.0.0.1:8000/api/chat')
    print(f'   Status: {resp.status_code}')
    acao = resp.headers.get('Access-Control-Allow-Origin', 'NOT FOUND')
    acma = resp.headers.get('Access-Control-Max-Age', 'NOT FOUND')
    print(f'   Access-Control-Allow-Origin: {acao}')
    print(f'   Access-Control-Max-Age: {acma}')

    print()
    print('8. Testing refresh token...')
    resp = requests.post('http://127.0.0.1:8000/api/auth/refresh', json={'refresh_token': refresh_token})
    print(f'   Status: {resp.status_code}')
    if resp.status_code == 200:
        print('   Refresh token works')
    else:
        print(f'   Refresh failed: {resp.text}')

    print()
    print('=== All Tests Completed ===')

if __name__ == '__main__':
    run_security_tests()
