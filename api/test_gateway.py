import pytest
from fastapi.testclient import TestClient
from main import app
import httpx
from httpx import Response
import json

client = TestClient(app)

class MockAsyncClient:
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    def build_request(self, method, url, **kwargs):
        class MockRequest:
            pass
        req = MockRequest()
        req.url = url
        return req
        
    async def send(self, request, stream=False):
        class MockResponse:
            def __init__(self, content, status_code=200):
                self.content = content
                self.status_code = status_code
                self.headers = {"content-type": "application/json"}
                
            async def aiter_raw(self):
                yield self.content
                
        # Simulate Ollama response depending on URL path
        if "api/generate" in str(request.url):
            return MockResponse(json.dumps({"model": "test-model", "response": "Hello World!"}).encode('utf-8'))
        return MockResponse(b"OK")
        
    async def aclose(self):
        pass

# Patch httpx.AsyncClient during tests
httpx.AsyncClient = MockAsyncClient

def test_gateway_no_auth():
    # Attempting to access without API key
    response = client.post("/gateway/api/generate", json={"model": "llama2", "prompt": "test"})
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]

def test_gateway_invalid_auth():
    # Attempting to access with invalid API key
    response = client.post("/gateway/api/generate", headers={"X-API-Key": "invalid-key"}, json={"model": "llama2", "prompt": "test"})
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]

def test_gateway_valid_auth_header():
    # Valid X-API-Key
    response = client.post("/gateway/api/generate", headers={"X-API-Key": "test-api-key-12345"}, json={"model": "llama2", "prompt": "test"})
    assert response.status_code == 200
    res = response.json()
    assert res["response"] == "Hello World!"

def test_gateway_valid_auth_bearer():
    # Valid Authorization Bearer
    response = client.post("/gateway/api/generate", headers={"Authorization": "Bearer test-api-key-12345"}, json={"model": "llama2", "prompt": "test"})
    assert response.status_code == 200
    res = response.json()
    assert res["response"] == "Hello World!"

def test_gateway_invalid_bearer():
    # Invalid Authorization Bearer
    response = client.post("/gateway/api/generate", headers={"Authorization": "Bearer wrong-key"}, json={"model": "llama2", "prompt": "test"})
    assert response.status_code == 401
    
if __name__ == "__main__":
    pytest.main(["-v", "test_gateway.py"])
