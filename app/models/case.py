# File: app/models/case.py
from app import db
from datetime import datetime

prefixes = db.relationship('BatesPrefix', backref='case', lazy='dynamic', cascade='all, delete-orphan')

@property
def bates_prefix(self):
    """Get the default Bates prefix for backward compatibility."""
    default_prefix = self.prefixes.filter_by(is_default=True).first()
    if default_prefix:
        return default_prefix.prefix
    return ""

@property
def current_sequence(self):
    """Get the current sequence from the default prefix."""
    default_prefix = self.prefixes.filter_by(is_default=True).first()
    if default_prefix:
        return default_prefix.current_sequence
    return 1

@current_sequence.setter
def current_sequence(self, value):
    """Set the current sequence on the default prefix."""
    default_prefix = self.prefixes.filter_by(is_default=True).first()
    if default_prefix:
        default_prefix.current_sequence = value

class Case(db.Model):
    """Case model for CoreText document management system."""
    
    __tablename__ = 'cases'
    
    id = db.Column(db.Integer, primary_key=True)
    case_name = db.Column(db.String(100), nullable=False)
    case_number = db.Column(db.String(50))
    #bates_prefix = db.Column(db.String(20), nullable=False)
    bates_prefix = db.Column(db.String(50), nullable=True)
    current_sequence = db.Column(db.Integer, default=1)
    description = db.Column(db.Text)
    custom_tags = db.relationship('Tag', backref='parent_case', lazy='dynamic')

    # Add relationship to BatesPrefix
    prefixes = db.relationship('BatesPrefix', backref='case', lazy='dynamic', cascade='all, delete-orphan')
    
    
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