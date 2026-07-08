import pytest
from app.models.user import User, Role

def test_user_registration_flow(client):
    # 1. Register a user
    register_payload = {
        "fullName": "Test Customer",
        "email": "testcustomer@example.com",
        "password": "securepassword123",
        "role": "USER",
        "phone": "9876543210"
    }
    
    response = client.post("/api/auth/register", json=register_payload)
    assert response.status_code == 201
    json_data = response.json()
    assert json_data["success"] is True
    assert "debugOtp" in json_data["data"]
    otp = json_data["data"]["debugOtp"]
    
    # 2. Verify OTP
    verify_payload = {
        "email": "testcustomer@example.com",
        "otp": otp
    }
    response_verify = client.post("/api/auth/verify-otp", json=verify_payload)
    assert response_verify.status_code == 200
    verify_data = response_verify.json()
    assert verify_data["success"] is True
    assert "token" in verify_data["data"]
    assert "refreshToken" in verify_data["data"]
    
    # 3. Login with credentials
    login_payload = {
        "email": "testcustomer@example.com",
        "password": "securepassword123"
    }
    response_login = client.post("/api/auth/login", json=login_payload)
    assert response_login.status_code == 200
    login_data = response_login.json()
    assert login_data["success"] is True
    assert login_data["data"]["user"]["fullName"] == "Test Customer"
