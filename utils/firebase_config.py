import json, os
import firebase_admin
from firebase_admin import auth, credentials, firestore

_app = None

def _init():
    global _app
    if _app is not None:
        return _app
    cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if cred_json:
        cred = credentials.Certificate(json.loads(cred_json))
        _app = firebase_admin.initialize_app(cred)
    elif cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        _app = firebase_admin.initialize_app(cred)
    else:
        _app = firebase_admin.initialize_app()
    return _app

def get_firestore():
    _init()
    return firestore.client()

def get_auth():
    _init()
    return auth
