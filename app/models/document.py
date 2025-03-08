# File: app/models/document.py
from app import db
from datetime import datetime

class Document(db.Model):
    """Document model for CoreText document management system."""
    
    __tablename__ = 'documents'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=False)
    
    # File information
    original_filename = db.Column(db.String(255), nullable=False)
    file_extension = db.Column(db.String(10), nullable=False)
    file_size = db.Column(db.Integer)  # Size in bytes
    
    # Bates numbering
    bates_number = db.Column(db.String(50), nullable=False)  # Base Bates number (e.g., ABC000001)
    bates_sequence = db.Column(db.Integer, nullable=False)   # Sequence number in case
    bates_start = db.Column(db.String(50), nullable=False)   # First page Bates (e.g., ABC000001-001)
    bates_end = db.Column(db.String(50), nullable=False)     # Last page Bates (e.g., ABC000001-042)
    page_count = db.Column(db.Integer, default=1)            # Number of pages
    
    # Storage information
    local_path = db.Column(db.String(255))                   # Local file path
    
    # Timestamps
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Document {self.bates_number} - {self.original_filename}>'
    
    @property
    def file_type_icon(self):
        """Return an appropriate icon class based on file extension."""
        ext = self.file_extension.lower()
        if ext in ['.pdf']:
            return 'bi-file-pdf'
        elif ext in ['.doc', '.docx']:
            return 'bi-file-word'
        elif ext in ['.xls', '.xlsx']:
            return 'bi-file-excel'
        elif ext in ['.jpg', '.jpeg', '.png', '.gif']:
            return 'bi-file-image'
        else:
            return 'bi-file-text'