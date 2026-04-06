from datetime import datetime
from extensions import db


class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'

    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(255), nullable=False, default='New Session')
    selected_ds_id   = db.Column(db.Integer, nullable=True)
    selected_doc_ids = db.Column(db.JSON, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':               self.id,
            'title':            self.title,
            'selected_ds_id':   self.selected_ds_id,
            'selected_doc_ids': self.selected_doc_ids or [],
            'created_at':       self.created_at.isoformat(),
            'updated_at':       self.updated_at.isoformat(),
        }


class Message(db.Model):
    __tablename__ = 'messages'

    id           = db.Column(db.Integer, primary_key=True)
    session_id   = db.Column(db.Integer, db.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False)
    role         = db.Column(db.String(20), nullable=False)   # 'user' | 'assistant'
    content      = db.Column(db.Text, nullable=False)
    html_content  = db.Column(db.Text, nullable=True)
    review_report = db.Column(db.JSON, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':            self.id,
            'session_id':    self.session_id,
            'role':          self.role,
            'content':       self.content,
            'html_content':  self.html_content,
            'review_report': self.review_report,
            'created_at':    self.created_at.isoformat(),
        }


class KnowledgeItem(db.Model):
    __tablename__ = 'knowledge_items'

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(255), nullable=False)
    filename     = db.Column(db.String(255), nullable=False)
    file_path    = db.Column(db.String(500), nullable=False)
    text_content = db.Column(db.Text, nullable=True)
    doc_type     = db.Column(db.String(50), nullable=False, default='general')
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':         self.id,
            'title':      self.title,
            'filename':   self.filename,
            'doc_type':   self.doc_type,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


class DesignSystem(db.Model):
    __tablename__ = 'design_systems'

    id           = db.Column(db.Integer, primary_key=True)
    org_id       = db.Column(db.Integer, nullable=True)
    name         = db.Column(db.String(255), nullable=False)
    pdf_filename = db.Column(db.String(255), nullable=True)
    tokens            = db.Column(db.JSON, nullable=True)
    brand_guidelines  = db.Column(db.JSON, nullable=True)
    slide_templates   = db.Column(db.JSON, nullable=True)
    is_default        = db.Column(db.Boolean, default=False, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assets = db.relationship('DesignSystemAsset', backref='design_system', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':           self.id,
            'name':         self.name,
            'pdf_filename': self.pdf_filename,
            'tokens':           self.tokens or {},
            'brand_guidelines': self.brand_guidelines or {},
            'slide_templates':  self.slide_templates or [],
            'is_default':       self.is_default,
            'created_at':   self.created_at.isoformat(),
            'updated_at':   self.updated_at.isoformat(),
        }


class DesignSystemAsset(db.Model):
    __tablename__ = 'design_system_assets'

    id               = db.Column(db.Integer, primary_key=True)
    design_system_id = db.Column(db.Integer, db.ForeignKey('design_systems.id'), nullable=False)
    name             = db.Column(db.String(255), nullable=False)
    asset_type       = db.Column(db.String(50), nullable=False)   # icon | logo | image
    file_url         = db.Column(db.String(500), nullable=False)
    filename         = db.Column(db.String(255), nullable=False)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':               self.id,
            'design_system_id': self.design_system_id,
            'name':             self.name,
            'asset_type':       self.asset_type,
            'file_url':         self.file_url,
            'filename':         self.filename,
            'created_at':       self.created_at.isoformat(),
        }
