import os
from google.cloud import secretmanager

def get_secret(secret_id, version="latest"):
    """Get secret from Secret Manager."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "coretext-452113")
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
    try:
        response = client.access_secret_version(name=name)
        return response.payload.data.decode('UTF-8')
    except Exception:
        return None

class Config:
    """Base configuration."""
    APP_NAME = "CoreText"
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-for-testing-only'
    GOOGLE_CLIENT_SECRETS_FILE = os.environ.get('GOOGLE_CLIENT_SECRETS_FILE') or 'credentials.json'
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    
    # Database configuration
    DB_USER = os.environ.get('DB_USER') or 'tryan'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or get_secret("coretext-db-password")
    DB_NAME = os.environ.get('DB_NAME') or 'coretext_db'
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    
    # For Cloud SQL with proxy
    CLOUD_SQL_CONNECTION_NAME = os.environ.get('CLOUD_SQL_CONNECTION_NAME') or 'coretext-452113:us-central1:coretext-db'
    
    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    # Local development SQLite database
    SQLALCHEMY_DATABASE_URI = 'sqlite:///coretext_dev.db'

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///coretext_test.db'

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    
    # Format for Cloud SQL Proxy
    SQLALCHEMY_DATABASE_URI = f"postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}/{Config.DB_NAME}?host=/cloudsql/{Config.CLOUD_SQL_CONNECTION_NAME}"

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
