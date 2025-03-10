from app import db
from datetime import datetime

class BatesPrefix(db.Model):
    __tablename__ = 'bates_prefixes'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=False)
    prefix = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    is_default = db.Column(db.Boolean, default=False)
    current_sequence = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<BatesPrefix {self.prefix}>'