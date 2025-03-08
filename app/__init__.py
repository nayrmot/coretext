from flask import Flask 
from flask_sqlalchemy import SQLAlchemy 
import os 
 
# Initialize extensions 
db = SQLAlchemy() 
 
def create_app(config_name='default'): 
    """Create and configure the Flask application.""" 
    app = Flask(__name__) 
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///coretext_dev.db' 
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False 
    app.config['SECRET_KEY'] = 'dev-secret-key' 
    app.config['UPLOAD_FOLDER'] = 'uploads' 
 
    # Initialize extensions with app 
    db.init_app(app) 
 
    # Ensure upload folder exists 
    uploads_dir = app.config.get('UPLOAD_FOLDER', 'uploads') 
    os.makedirs(uploads_dir, exist_ok=True) 
 
    # Register blueprints 
    try: 
        from app.routes import main_bp 
        app.register_blueprint(main_bp) 
    except ImportError: 
        pass  # Will add routes later 
 
    # Create database tables 
    with app.app_context(): 
        db.create_all() 
 
    return app 
