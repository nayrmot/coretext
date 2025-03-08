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
    mime_type = db.Column(db.String(100))
    
    # Bates numbering
    bates_number = db.Column(db.String(50), nullable=False)  # Base Bates number (e.g., ABC000001)
    bates_sequence = db.Column(db.Integer, nullable=False)   # Sequence number in case
    bates_start = db.Column(db.String(50), nullable=False)   # First page Bates (e.g., ABC000001-001)
    bates_end = db.Column(db.String(50), nullable=False)     # Last page Bates (e.g., ABC000001-042)
    page_count = db.Column(db.Integer, default=1)            # Number of pages
    
    # Storage information
    google_drive_id = db.Column(db.String(100))              # Google Drive file ID
    google_drive_path = db.Column(db.String(255))            # Google Drive file URL
    local_path = db.Column(db.String(255))                   # Optional local file path
    
    # Timestamps
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_accessed = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Document {self.bates_number} - {self.original_filename}>'
    
    def get_file_icon(self):
        """Return the appropriate icon class based on file extension."""
        if self.file_extension.lower() in ['.pdf']:
            return 'bi-file-pdf'
        elif self.file_extension.lower() in ['.doc', '.docx']:
            return 'bi-file-word'
        elif self.file_extension.lower() in ['.xls', '.xlsx']:
            return 'bi-file-excel'
        elif self.file_extension.lower() in ['.jpg', '.jpeg', '.png', '.gif']:
            return 'bi-file-image'
        else:
            return 'bi-file-text'
    
    def get_bates_range_display(self):
        """Get a human-readable representation of the Bates range."""
        if self.bates_start == self.bates_end:
            return self.bates_start
        return f"{self.bates_start} - {self.bates_end}"
