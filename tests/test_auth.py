import pytest
from unittest.mock import patch
from app.models.user import User, Role

@patch("app.api.auth.verify_firebase_token")
def test_firebase_login_new_user(mock_verify, client):
    # Mock Firebase claims for a new phone user
    mock_verify.return_value = {
        "uid": "new-firebase-uid-123",
        "phone_number": "+919876543210",
        "name": "Firebase User",
        "firebase": {
            "sign_in_provider": "phone"
        }
    }
    
    payload = {
        "idToken": "mock-firebase-token-123",
        "fullName": "Firebase User",
        "role": "USER"
    }
    
    response = client.post("/api/auth/firebase-login", json=payload)
    assert response.status_code == 200
    json_data = response.json()
    
    assert json_data["success"] is True
    assert "accessToken" in json_data
    assert "refreshToken" in json_data
    assert json_data["user"]["fullName"] == "Firebase User"
    assert json_data["user"]["phone"] == "+919876543210"
    assert json_data["user"]["role"] == "USER"


@patch("app.api.auth.verify_firebase_token")
def test_firebase_login_existing_user(mock_verify, client):
    # 1. First, create a user using the firebase-login flow
    mock_verify.return_value = {
        "uid": "existing-uid-456",
        "phone_number": "+919999999999",
        "name": "Existing User",
        "firebase": {
            "sign_in_provider": "phone"
        }
    }
    
    payload = {
        "idToken": "mock-token-456",
        "fullName": "Existing User",
        "role": "USER"
    }
    
    response1 = client.post("/api/auth/firebase-login", json=payload)
    assert response1.status_code == 200
    
    # 2. Login again with the same Firebase UID
    response2 = client.post("/api/auth/firebase-login", json={"idToken": "mock-token-456"})
    assert response2.status_code == 200
    json_data = response2.json()
    assert json_data["success"] is True
    assert json_data["user"]["fullName"] == "Existing User"
    assert json_data["user"]["phone"] == "+919999999999"


@patch("app.api.auth.verify_firebase_token")
def test_firebase_login_google_sign_in(mock_verify, client):
    # Mock Google claims
    mock_verify.return_value = {
        "uid": "google-uid-789",
        "email": "googleuser@example.com",
        "name": "Google User",
        "picture": "https://example.com/pic.jpg",
        "firebase": {
            "sign_in_provider": "google.com"
        }
    }
    
    payload = {
        "idToken": "mock-google-token-789",
        "fullName": "Google User",
        "role": "USER"
    }
    
    response = client.post("/api/auth/firebase-login", json=payload)
    assert response.status_code == 200
    json_data = response.json()
    
    assert json_data["success"] is True
    assert json_data["user"]["email"] == "googleuser@example.com"
    assert json_data["user"]["fullName"] == "Google User"
    assert json_data["user"]["profileImage"] == "https://example.com/pic.jpg"
