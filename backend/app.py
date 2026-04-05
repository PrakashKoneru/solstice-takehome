import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from dotenv import load_dotenv

load_dotenv()

from extensions import db, migrate


def create_app():
    app = Flask(__name__)

    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/solstice'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app, origins=['http://localhost:3000'])

    from models import ChatSession
    admin = Admin(app, name='ContentStudio', template_mode='bootstrap3')
    admin.add_view(ModelView(ChatSession, db.session))

    from routes.sessions import sessions_bp
    app.register_blueprint(sessions_bp)

    @app.route('/api/health')
    def health():
        return jsonify({'status': 'ok'})

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
