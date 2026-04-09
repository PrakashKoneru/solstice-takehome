import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from dotenv import load_dotenv

load_dotenv()

from extensions import db, migrate, socketio


def create_app():
    app = Flask(__name__)

    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/solstice')
    # psycopg3 requires postgresql+psycopg:// scheme
    if db_url.startswith('postgresql://') or db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
        db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    socketio.init_app(app, cors_allowed_origins='*', async_mode='threading')

    from models import ChatSession, KnowledgeItem, DesignSystem, DesignSystemAsset, Message
    admin = Admin(app, name='ContentStudio', template_mode='bootstrap3')
    admin.add_view(ModelView(ChatSession, db.session))
    admin.add_view(ModelView(Message, db.session))
    admin.add_view(ModelView(KnowledgeItem, db.session))
    admin.add_view(ModelView(DesignSystem, db.session))
    admin.add_view(ModelView(DesignSystemAsset, db.session))

    from routes.sessions import sessions_bp
    from routes.design_system import design_system_bp
    from routes.knowledge import knowledge_bp
    from routes.chat import chat_bp
    import routes.presence  # noqa: F401 — registers Socket.IO event handlers
    app.register_blueprint(sessions_bp)
    app.register_blueprint(design_system_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(chat_bp)

    @app.route('/api/health')
    def health():
        return jsonify({'status': 'ok'})

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    return app


app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5001)
