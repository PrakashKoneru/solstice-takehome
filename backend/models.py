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
    doc_type           = db.Column(db.String(50), nullable=False, default='general')
    doc_outline        = db.Column(db.JSON, nullable=True)
    extraction_status  = db.Column(db.String(20), default='pending')
    total_pages        = db.Column(db.Integer, nullable=True)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at         = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':                self.id,
            'title':             self.title,
            'filename':          self.filename,
            'doc_type':          self.doc_type,
            'doc_outline':       self.doc_outline or [],
            'extraction_status': self.extraction_status,
            'total_pages':       self.total_pages,
            'created_at':        self.created_at.isoformat(),
            'updated_at':        self.updated_at.isoformat(),
        }


class DesignSystem(db.Model):
    __tablename__ = 'design_systems'

    id           = db.Column(db.Integer, primary_key=True)
    org_id       = db.Column(db.Integer, nullable=True)
    name         = db.Column(db.String(255), nullable=False)
    pdf_filename = db.Column(db.String(255), nullable=True)
    tokens            = db.Column(db.JSON, nullable=True)
    brand_guidelines  = db.Column(db.JSON, nullable=True)
    component_patterns = db.Column(db.JSON, nullable=True)
    extraction_status  = db.Column(db.String(20), default='complete', nullable=False)
    extraction_step    = db.Column(db.String(50), nullable=True)
    is_default         = db.Column(db.Boolean, default=False, nullable=False)
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
            'component_patterns':  self.component_patterns or {},
            'extraction_status':   self.extraction_status or 'complete',
            'extraction_step':     self.extraction_step,
            'is_default':          self.is_default,
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
    source           = db.Column(db.String(50), nullable=False, default='raster')  # claude_crop | raster
    page_number      = db.Column(db.Integer, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':               self.id,
            'design_system_id': self.design_system_id,
            'name':             self.name,
            'asset_type':       self.asset_type,
            'file_url':         self.file_url,
            'filename':         self.filename,
            'source':           self.source,
            'page_number':      self.page_number,
            'created_at':       self.created_at.isoformat(),
        }


class Chunk(db.Model):
    __tablename__ = 'chunks'

    id              = db.Column(db.String(64), primary_key=True)
    knowledge_id    = db.Column(db.Integer, db.ForeignKey('knowledge_items.id', ondelete='CASCADE'), nullable=False)
    headings        = db.Column(db.JSON, nullable=True)       # ["5. WARNINGS", "5.2 Hemorrhagic Events"]
    serialized_text = db.Column(db.Text, nullable=True)       # heading path + content (what's embedded)
    element_types   = db.Column(db.JSON, nullable=True)       # ["paragraph", "list_item", "table"]
    has_table       = db.Column(db.Boolean, default=False)
    has_figure      = db.Column(db.Boolean, default=False)
    page_start      = db.Column(db.Integer, nullable=True)
    page_end        = db.Column(db.Integer, nullable=True)
    embedding       = db.Column(db.JSON, nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    claims = db.relationship('Claim', backref='chunk', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':              self.id,
            'knowledge_id':    self.knowledge_id,
            'headings':        self.headings or [],
            'serialized_text': self.serialized_text,
            'element_types':   self.element_types or [],
            'has_table':       self.has_table,
            'has_figure':      self.has_figure,
            'page_start':      self.page_start,
            'page_end':        self.page_end,
            'created_at':      self.created_at.isoformat(),
        }


class Claim(db.Model):
    __tablename__ = 'claims'

    id              = db.Column(db.String(64), primary_key=True)   # "{drug}_{type}_{study}_{seq}"
    chunk_id        = db.Column(db.String(64), db.ForeignKey('chunks.id', ondelete='SET NULL'), nullable=True)
    knowledge_id    = db.Column(db.Integer, db.ForeignKey('knowledge_items.id', ondelete='CASCADE'), nullable=False)
    text            = db.Column(db.Text, nullable=False)           # verbatim, immutable after approval
    claim_type      = db.Column(db.String(32), nullable=False)
    # efficacy | safety | dosing | moa | isi | boilerplate | stat | study_design | indication | nccn
    content_format  = db.Column(db.String(16), nullable=False, default='text')  # text | table | figure
    table_markdown  = db.Column(db.Text, nullable=True)
    table_json      = db.Column(db.JSON, nullable=True)           # {"headers": [...], "rows": [[...], ...]}
    figure_url      = db.Column(db.String(500), nullable=True)
    source_citation = db.Column(db.String(255), nullable=True)
    page_number     = db.Column(db.Integer, nullable=True)
    numeric_values  = db.Column(db.JSON, nullable=True)
    # [{"value": "7.4", "unit": "months", "label": "median OS (FRUZAQLA)"}]
    tags            = db.Column(db.JSON, nullable=True)
    section         = db.Column(db.String(255), nullable=True)
    section_hierarchy = db.Column(db.JSON, nullable=True)  # ["5. WARNINGS", "5.5. Hepatotoxicity"]
    embedding       = db.Column(db.JSON, nullable=True)   # list of floats from OpenAI embedding
    is_approved     = db.Column(db.Boolean, default=True, nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':              self.id,
            'chunk_id':        self.chunk_id,
            'knowledge_id':    self.knowledge_id,
            'text':            self.text,
            'claim_type':      self.claim_type,
            'content_format':  self.content_format or 'text',
            'table_markdown':  self.table_markdown,
            'table_json':      self.table_json,
            'figure_url':      self.figure_url,
            'source_citation': self.source_citation,
            'page_number':     self.page_number,
            'numeric_values':  self.numeric_values or [],
            'tags':            self.tags or [],
            'section':         self.section,
            'section_hierarchy': self.section_hierarchy or [],
            'is_approved':     self.is_approved,
            'created_at':      self.created_at.isoformat(),
        }
