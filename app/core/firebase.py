import os
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException, status

# Global flag to track initialization
_firebase_initialized = False

def initialize_firebase():
    global _firebase_initialized
    if _firebase_initialized or firebase_admin._apps:
        _firebase_initialized = True
        return

    # 1. Try GOOGLE_APPLICATION_CREDENTIALS path
    google_app_creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    service_account_path = "serviceAccountKey.json"

    if google_app_creds and os.path.exists(google_app_creds):
        try:
            cred = credentials.Certificate(google_app_creds)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            print("Firebase Admin SDK initialized successfully via GOOGLE_APPLICATION_CREDENTIALS.")
            return
        except Exception as e:
            print(f"Error initializing Firebase via GOOGLE_APPLICATION_CREDENTIALS: {e}")

    # 2. Try serviceAccountKey.json in the current working directory
    if os.path.exists(service_account_path):
        try:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            print("Firebase Admin SDK initialized successfully via serviceAccountKey.json.")
            return
        except Exception as e:
            print(f"Error initializing Firebase via serviceAccountKey.json: {e}")

    # 3. Try individual env variables: FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY
    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    client_email = os.environ.get("FIREBASE_CLIENT_EMAIL")
    private_key = os.environ.get("FIREBASE_PRIVATE_KEY")

    if project_id and client_email and private_key:
        try:
            # Fix escaped newline character if passed as string literal
            formatted_private_key = private_key.replace("\\n", "\n")
            cred_dict = {
                "type": "service_account",
                "project_id": project_id,
                "private_key": formatted_private_key,
                "client_email": client_email,
                "token_url": "https://oauth2.googleapis.com/token",
            }
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            print("Firebase Admin SDK initialized successfully via environment variables.")
            return
        except Exception as e:
            print(f"Error initializing Firebase via environment variables: {e}")

    # 4. Fallback to application default credentials
    try:
        firebase_admin.initialize_app()
        _firebase_initialized = True
        print("Firebase Admin SDK initialized successfully using default application credentials.")
    except Exception as e:
        print(f"Warning: Firebase Admin SDK failed to initialize. Claims verification will fail. Error: {e}")

# Initialize at module load time
initialize_firebase()

def verify_firebase_token(id_token: str) -> dict:
    """
    Verifies a Firebase ID token.
    Raises HTTPException if verification fails.
    """
    if not _firebase_initialized:
        # Re-try initialization just in case env variables were loaded later
        initialize_firebase()
        if not _firebase_initialized:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Firebase Admin SDK is not initialized."
            )
            
    try:
        # Verify the token, check_revoked=True rejects revoked tokens
        decoded_token = auth.verify_id_token(id_token, check_revoked=True)
        return decoded_token
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase ID Token has expired."
        )
    except auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase ID Token has been revoked."
        )
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase ID Token is invalid."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Firebase ID Token verification failed: {str(e)}"
        )
