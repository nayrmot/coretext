from app import db

class DocumentTag(db.Model):
    __tablename__ = 'document_tags'

    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), primary_key=True)

    # Explicit relationship definitions
    document = db.relationship(
        'Document',
        back_populates='tag_associations',
        overlaps="tags,documents"
    )

    tag = db.relationship(
        'Tag',
        back_populates='document_associations',
        overlaps="documents,tags"
    )

    def __repr__(self):
        return f"<DocumentTag(document_id={self.document_id}, tag_id={self.tag_id})>"
