from flask import Flask, render_template, flash, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
import os

# Initialize extensions
db = SQLAlchemy()


def create_default_tags(app):
    with app.app_context():
        from app.models.tag import Tag
        
        # Check if default tags already exist
        if Tag.query.filter_by(is_default=True).count() > 0:
            return
        
        # Create default tags
        default_tags = [
            {'name': 'Contract', 'color': '#0d6efd'},  # Blue
            {'name': 'Email', 'color': '#6610f2'},     # Purple
            {'name': 'Invoice', 'color': '#fd7e14'},   # Orange
            {'name': 'Letter', 'color': '#198754'},    # Green
            {'name': 'Memo', 'color': '#dc3545'},      # Red
            {'name': 'Pleading', 'color': '#0dcaf0'},  # Cyan
            {'name': 'Evidence', 'color': '#fd7e14'},  # Orange
            {'name': 'Exhibit', 'color': '#d63384'},   # Pink
        ]
        
        for tag_data in default_tags:
            tag = Tag(name=tag_data['name'], color=tag_data['color'], is_default=True)
            db.session.add(tag)
        
        db.session.commit()

        
def create_app(config_name='default'):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'dev-key-for-coretext'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///coretext.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    
    # Create uploads folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions with app
    db.init_app(app)
    
    # Home page
    @app.route('/')
    def index():
        return render_template('index.html', title="CoreText Home")
    
    # List all cases
    @app.route('/cases')
    def cases():
        from app.models.case import Case
        cases = Case.query.all()
        return render_template('cases.html', title="All Cases", cases=cases)
    
    # Create a new case
    @app.route('/case/new', methods=['GET', 'POST'])
    def new_case():
        from app.models.case import Case
        if request.method == 'POST':
            case_name = request.form['case_name']
            case_number = request.form.get('case_number', '')
            bates_prefix = request.form.get('bates_prefix', '')
            description = request.form.get('description', '')
            
            # If no Bates prefix provided, generate one from case name
            if not bates_prefix:
                words = case_name.split()
                bates_prefix = ''.join(word[0].upper() for word in words if word)
            
            # Create case in database
            case = Case(
                case_name=case_name,
                case_number=case_number,
                bates_prefix=bates_prefix,
                description=description
            )
            db.session.add(case)
            db.session.commit()
            
            flash(f"Case '{case_name}' created successfully", "success")
            return redirect(url_for('cases'))
        
        return render_template('new_case.html', title="New Case")
    
    # View case details
    @app.route('/case/<int:case_id>')
    def view_case(case_id):
        from app.models.case import Case
        from app.models.document import Document
        case = Case.query.get_or_404(case_id)
        documents = Document.query.filter_by(case_id=case_id).all()
        return render_template('case.html', title=case.case_name, case=case, documents=documents)
    
    # Upload document to a case
    @app.route('/case/<int:case_id>/upload', methods=['GET', 'POST'])
    def upload_document(case_id):
        from app.models.case import Case
        from app.utils.bates import BatesManager
        
        case = Case.query.get_or_404(case_id)
        
        if request.method == 'POST':
            if 'file' not in request.files:
                flash('No file selected', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            if file.filename == '':
                flash('No file selected', 'error')
                return redirect(request.url)
            
            # Process the file with Bates manager
            bates_manager = BatesManager()
            try:
                document = bates_manager.process_document(
                    case_id,
                    file,
                    app.config['UPLOAD_FOLDER']
                )
                flash(f'Document uploaded and assigned Bates number: {document.bates_number}', 'success')
            except Exception as e:
                flash(f'Error processing document: {str(e)}', 'error')
            
            return redirect(url_for('view_case', case_id=case_id))
        
        return render_template('upload_document.html', title="Upload Document", case=case)
    
    # Download document
    @app.route('/document/<int:document_id>/download')
    def download_document(document_id):
        from app.models.document import Document
        from flask import send_file
        
        document = Document.query.get_or_404(document_id)
        
        if document.local_path and os.path.exists(document.local_path):
            return send_file(
                document.local_path,
                as_attachment=True,
                download_name=document.original_filename
            )
        else:
            flash("Document file not found", "error")
            return redirect(url_for('view_case', case_id=document.case_id))
    
    # View document
    @app.route('/document/<int:document_id>/view')
    def view_document(document_id):
        from app.models.document import Document
        from flask import send_file
    
        document = Document.query.get_or_404(document_id)
    
        if document.local_path and os.path.exists(document.local_path):
            # For PDF files, display inline in browser
            return send_file(
                document.local_path,
                mimetype='application/pdf' if document.file_extension.lower() == '.pdf' else None,
                as_attachment=False  # This makes it display in browser instead of downloading
            )
        else:
            flash("Document file not found", "error")
            return redirect(url_for('view_case', case_id=document.case_id))
    
    # Document details
    @app.route('/document/<int:document_id>')
    def document_details(document_id):
        from app.models.document import Document
        from app.models.case import Case
        
        document = Document.query.get_or_404(document_id)
        case = Case.query.get(document.case_id)
        
        return render_template('document_details.html', 
                            title=document.original_filename, 
                            document=document, 
                            case=case)
    
    # Search documents
    @app.route('/search')
    def search():
        from app.models.case import Case
        from app.utils.bates import BatesManager
        
        query = request.args.get('q', '')
        case_id = request.args.get('case_id', type=int)
        
        cases = Case.query.all()
        results = []
        
        if query or case_id:
            bates_manager = BatesManager()
            results = bates_manager.search_documents(
                case_id=case_id,
                bates_number=query,
                filename=query
            )
    
        return render_template('search.html', title="Search Documents", 
                            results=results, cases=cases)   
    
    # Batch upload
    @app.route('/case/<int:case_id>/batch-upload', methods=['GET', 'POST'])
    def batch_upload(case_id):
        from app.models.case import Case
        from app.utils.bates import BatesManager
        
        case = Case.query.get_or_404(case_id)
        
        if request.method == 'POST':
            if 'files[]' not in request.files:
                flash('No files selected', 'error')
                return redirect(request.url)
                
            files = request.files.getlist('files[]')
            if not files or files[0].filename == '':
                flash('No files selected', 'error')
                return redirect(request.url)
                
            bates_manager = BatesManager()
            processed_count = 0
            
            for file in files:
                if file.filename == '':
                    continue
                    
                try:
                    document = bates_manager.process_document(case_id, file, app.config['UPLOAD_FOLDER'])
                    processed_count += 1
                except Exception as e:
                    flash(f'Error processing {file.filename}: {str(e)}', 'error')
                    
            flash(f'Successfully processed {processed_count} documents', 'success')
            return redirect(url_for('view_case', case_id=case_id))
        
        return render_template('batch_upload.html', title="Batch Upload", case=case)
    
    # Tag management
    @app.route('/tags')
    def list_tags():
        from app.models.tag import Tag
        default_tags = Tag.query.filter_by(is_default=True).all()
        custom_tags = Tag.query.filter_by(is_default=False).order_by(Tag.case_id).all()
        return render_template('tags.html', title="Manage Tags", 
                            default_tags=default_tags, 
                            custom_tags=custom_tags)

    @app.route('/case/<int:case_id>/tags', methods=['GET', 'POST'])
    def case_tags(case_id):
        from app.models.case import Case
        from app.models.tag import Tag
        
        case = Case.query.get_or_404(case_id)
        
        if request.method == 'POST':
            tag_name = request.form.get('tag_name')
            tag_color = request.form.get('tag_color', '#6c757d')
            
            if not tag_name:
                flash('Tag name is required', 'error')
                return redirect(url_for('case_tags', case_id=case_id))
            
            # Check if tag already exists for this case
            existing_tag = Tag.query.filter_by(name=tag_name, case_id=case_id).first()
            if existing_tag:
                flash(f'Tag "{tag_name}" already exists for this case', 'error')
                return redirect(url_for('case_tags', case_id=case_id))
            
            # Create new tag
            tag = Tag(name=tag_name, color=tag_color, case_id=case_id)
            db.session.add(tag)
            db.session.commit()
            
            flash(f'Tag "{tag_name}" created successfully', 'success')
            return redirect(url_for('case_tags', case_id=case_id))
        
        # Get all available tags for this case (default + case-specific)
        default_tags = Tag.query.filter_by(is_default=True).all()
        case_tags = Tag.query.filter_by(case_id=case_id).all()
        
        return render_template('case_tags.html', title=f"Tags for {case.case_name}", 
                            case=case, 
                            default_tags=default_tags, 
                            case_tags=case_tags)

    @app.route('/tag/<int:tag_id>/delete', methods=['POST'])
    def delete_tag(tag_id):
        from app.models.tag import Tag
        
        tag = Tag.query.get_or_404(tag_id)
        
        # Don't allow deleting default tags
        if tag.is_default:
            flash('Cannot delete default tags', 'error')
            return redirect(url_for('list_tags'))
        
        case_id = tag.case_id
        
        # Delete the tag
        db.session.delete(tag)
        db.session.commit()
        
        flash(f'Tag "{tag.name}" deleted successfully', 'success')
        
        # Redirect back to case tags if from a case, otherwise to main tags page
        if case_id:
            return redirect(url_for('case_tags', case_id=case_id))
        else:
            return redirect(url_for('list_tags'))

    @app.route('/document/<int:document_id>/tags', methods=['GET', 'POST'])
    def document_tags(document_id):
        from app.models.document import Document
        from app.models.case import Case
        from app.models.tag import Tag
        
        document = Document.query.get_or_404(document_id)
        case = Case.query.get(document.case_id)
        
        if request.method == 'POST':
            # Get selected tag IDs
            tag_ids = request.form.getlist('tag_ids')
            
            # Remove all existing tags
            document.tags = []
            
            # Add selected tags
            if tag_ids:
                for tag_id in tag_ids:
                    tag = Tag.query.get(tag_id)
                    if tag:
                        document.tags.append(tag)
            
            db.session.commit()
            flash('Document tags updated successfully', 'success')
            return redirect(url_for('document_details', document_id=document_id))
        
        # Get all available tags for this case (default + case-specific)
        default_tags = Tag.query.filter_by(is_default=True).all()
        case_tags = Tag.query.filter_by(case_id=document.case_id).all()
        all_tags = default_tags + case_tags
        
        # Get currently assigned tags
        current_tag_ids = [tag.id for tag in document.tags]
        
        return render_template('document_tags.html', 
                            title=f"Manage Tags for {document.original_filename}", 
                            document=document, 
                            case=case, 
                            all_tags=all_tags, 
                            current_tag_ids=current_tag_ids)
    
    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html', title='Page Not Found'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html', title='Server Error'), 500
    
    # Create database tables
    with app.app_context():
        # Import models here to avoid circular imports
        from app.models.case import Case
        from app.models.document import Document
        from app.models.tag import Tag
        db.create_all()
        create_default_tags(app)
    
    return app