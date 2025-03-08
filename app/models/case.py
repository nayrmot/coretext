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
    
    # Google Drive folder information
    drive_folder_id = db.Column(db.String(100))
    drive_folder_url = db.Column(db.String(255))
    
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
    def total_pages(self):
        """Get the total number of pages across all documents in this case."""
        return sum(doc.page_count or 0 for doc in self.documents)
    
    @property
    def next_bates_number(self):
        """Get the next formatted Bates number that will be assigned."""
        return f"{self.bates_prefix}{str(self.current_sequence).zfill(6)}"
    
    def get_bates_range(self):
        """Get the full range of Bates numbers used in this case."""
        if not self.documents:
            return None, None
            
        start_bates = min(doc.bates_start for doc in self.documents if doc.bates_start)
        end_bates = max(doc.bates_end for doc in self.documents if doc.bates_end)
        
        return start_bates, end_bates
