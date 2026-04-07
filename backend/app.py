import os
from flask import Flask, jsonify, send_from_directory
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
    CORS(app, origins=[
        'http://localhost:3000',
        'https://frontend-ten-umber-51.vercel.app',
        r'https://.*\.vercel\.app',
    ])

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
    app.run(debug=True, port=5001)
