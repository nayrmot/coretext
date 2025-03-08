from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "<h1>Hello from CoreText!</h1><p>If you can see this, Flask is working correctly.</p>"

if __name__ == '__main__':
    app.run(debug=True, port=5001)