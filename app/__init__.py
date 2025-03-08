from flask import Flask, render_template

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'dev-key-for-testing'
    
    # Define basic routes for testing
    @app.route('/')
    def index():
        return "<h1>Welcome to CoreText</h1><p>Your document management system is running correctly.</p>"
    
    # Try adding a basic case route
    @app.route('/cases')
    def cases():
        return "<h1>Cases</h1><p>This will show your list of cases.</p>"
    
    return app