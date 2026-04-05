from datetime import datetime
from extensions import db


class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'

    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(255), nullable=False, default='New Session')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':         self.id,
            'title':      self.title,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
