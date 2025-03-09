from app import db
from datetime import datetime

class Tag(db.Model):
    __tablename__ = 'tags'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#6c757d")  # Default gray color
    is_default = db.Column(db.Boolean, default=False)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=True)  # Null for default tags
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Change the backref name to avoid conflicts
    case = db.relationship('Case', backref=db.backref('case_tags', lazy='dynamic'), overlaps="custom_tags,parent_case")
    
    def __repr__(self):
        return f'<Tag {self.name}>'


class DocumentTag(db.Model):
    __tablename__ = 'document_tags'
    
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), primary_key=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    document = db.relationship('Document', backref=db.backref('tag_associations', cascade='all, delete-orphan'))
    tag = db.relationship('Tag', backref=db.backref('document_associations', cascade='all, delete-orphan'))