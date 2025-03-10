from app import db
from datetime import datetime
from app.models.document_tag import DocumentTag

class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#6c757d")
    is_default = db.Column(db.Boolean, default=False)

    documents = db.relationship(
        'Document',
        secondary='document_tags',
        back_populates='tags',
        overlaps="document_associations,tag_associations"
    )

    document_associations = db.relationship(
        'DocumentTag',
        back_populates='tag',
        overlaps="documents,tags"
    )

    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'))
    parent_case = db.relationship(
        'Case',
        back_populates='custom_tags',
        overlaps="case_tags"
    )

    def __repr__(self):
        return f'<Tag {self.name}>'
