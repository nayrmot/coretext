# File: app/models/case.py
from app import db
from datetime import datetime

class Case(db.Model):
    """Case model for CoreText document management system."""
    
    __tablename__ = 'cases'
    
    id = db.Column(db.Integer, primary_key=True)
    case_name = db.Column(db.String(100), nullable=False)
    case_number = db.Column(db.String(50))
    bates_prefix = db.Column(db.String(20), nullable=False)
    current_sequence = db.Column(db.Integer, default=1)
    description = db.Column(db.Text)
    custom_tags = db.relationship('Tag', backref='parent_case', lazy='dynamic')
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    documents = db.relationship('Document', backref='case', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Case {self.case_name}>'
    
    @property
    def document_count(self):
        """Get the number of documents in this case."""
        return len(self.documents)
    
    @property
    def next_bates_number(self):
        """Get the next formatted Bates number that will be assigned."""
        return f"{self.bates_prefix}{str(self.current_sequence).zfill(6)}"