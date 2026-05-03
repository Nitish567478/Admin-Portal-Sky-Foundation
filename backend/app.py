from flask import Flask
from flask_login import LoginManager
from config import Config
from models import db, Admin
from routes import init_routes

app = Flask(__name__, static_folder='sky', static_url_path='', template_folder='sky')
app.config.from_object(Config)

# Initialize DB
db.init_app(app)

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = '/'

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id)) if user_id else None

# Initialize routes
init_routes(app, login_manager)

# Create tables
with app.app_context():
    db.create_all()

# Run locally only
if __name__ == "__main__":
    app.run(debug=True)