from flask import Flask, render_template, flash, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate  # <-- Import Flask-Migrate
import logging
from logging.handlers import RotatingFileHandler
import os

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()  # <-- Initialize Migrate

def configure_logging():
    log_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(log_folder, exist_ok=True)
    
    # Configure rotating file handler instead of regular file handler
    file_handler = RotatingFileHandler(
        os.path.join(log_folder, 'coretext.log'),
        maxBytes=10485760,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    
    # Configure formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    
    return logger

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

    # Configure logging
    logger = configure_logging()
    app.logger = logger
    
    # Configuration
    app.config['SECRET_KEY'] = 'dev-key-for-coretext'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///coretext.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    
    # Create uploads folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)  # <-- Initialize migrate after db.init_app

    # Add datetime filter
    @app.template_filter('datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M'):
        """Format a datetime object to a string."""
        if value is None:
            return ""
        
        # If it's a string, try to parse it
        if isinstance(value, str):
            try:
                from dateutil import parser
                value = parser.parse(value)
            except:
                return value
        
        # Format the datetime
        try:
            return value.strftime(format)
        except:
            return str(value)
    
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
        from app.models.bates_prefix import BatesPrefix
        
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
                description=description,
                bates_prefix=bates_prefix  # Temporarily keep setting this
            )
            db.session.add(case)
            db.session.commit()
            
            # Create the default prefix
            prefix = BatesPrefix(
                case_id=case.id,
                prefix=bates_prefix,
                description="Default prefix",
                is_default=True,
                current_sequence=1
            )
            db.session.add(prefix)
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
        from app.models.bates_prefix import BatesPrefix
        from app.utils.bates import BatesManager
        
        case = Case.query.get_or_404(case_id)
        prefixes = BatesPrefix.query.filter_by(case_id=case_id).all()
        
        if not prefixes:
            flash('You need to define at least one Bates prefix for this case', 'error')
            return redirect(url_for('case_prefixes', case_id=case_id))
        
        if request.method == 'POST':
            if 'file' not in request.files:
                flash('No file selected', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            if file.filename == '':
                flash('No file selected', 'error')
                return redirect(request.url)
            
            # Get selected prefix or use default
            prefix_id = request.form.get('prefix_id')
            try:
                prefix_id = int(prefix_id)
                prefix = BatesPrefix.query.filter_by(id=prefix_id, case_id=case_id).first()
            except (ValueError, TypeError):
                prefix = BatesPrefix.query.filter_by(case_id=case_id, is_default=True).first()
            
            if not prefix:
                flash('Selected prefix not found', 'error')
                return redirect(request.url)
            
            # Get option for handling existing Bates
            force_relabel = 'force_relabel' in request.files
            
            # Process the file with Bates manager
            bates_manager = BatesManager()
            try:
                document = bates_manager.process_document_with_prefix(
                    case_id,
                    file,
                    app.config['UPLOAD_FOLDER'],
                    prefix,
                    force_relabel=force_relabel
                )
                
                # Create a more detailed flash message
                if hasattr(document, 'existing_bates') and document.existing_bates:
                    flash(f'Document uploaded. Existing Bates numbers detected: {document.bates_note}', 'info')
                elif document.page_count > 1:
                    flash(f'Document uploaded with {document.page_count} pages. Bates range: {document.bates_start} to {document.bates_end}', 'success')
                else:
                    flash(f'Document uploaded and assigned Bates number: {document.bates_number}', 'success')
                    
            except Exception as e:
                flash(f'Error processing document: {str(e)}', 'error')
            
            return redirect(url_for('view_case', case_id=case_id))
        
        return render_template('upload_document.html', title="Upload Document", case=case, prefixes=prefixes)
    
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
    
    @app.route('/document/<int:document_id>/edit-bates', methods=['GET', 'POST'])
    def edit_bates(document_id):
        from app.models.document import Document
        from app.models.case import Case
        from app.utils.bates import BatesManager
        
        document = Document.query.get_or_404(document_id)
        case = Case.query.get(document.case_id)
        
        if request.method == 'POST':
            new_bates_start = request.form.get('bates_number', '').strip()
            
            if not new_bates_start:
                flash('Bates number cannot be empty', 'error')
                return redirect(url_for('edit_bates', document_id=document_id))
            
            # Parse the new starting Bates number to get prefix and sequence
            parts = new_bates_start.split('-')
            if len(parts) < 2:
                flash('Bates number must be in format Prefix-Number', 'error')
                return redirect(url_for('edit_bates', document_id=document_id))
            
            try:
                # Get the prefix (everything before the last component)
                prefix = '-'.join(parts[:-1])
                # Get the sequence number (last component)
                start_sequence = int(parts[-1])
            except ValueError:
                flash('Invalid Bates number format', 'error')
                return redirect(url_for('edit_bates', document_id=document_id))
            
            # Calculate the ending Bates number
            end_sequence = start_sequence + document.page_count - 1
            new_bates_end = f"{prefix}-{str(end_sequence).zfill(6)}"
            
            # Check if the Bates range overlaps with any other document in this case
            overlap = Document.query.filter(
                Document.case_id == document.case_id,
                Document.id != document.id,
                db.or_(
                    # Check if any document's bates range overlaps with our new range
                    db.and_(
                        # Other doc's start <= our end
                        db.func.cast(db.func.substr(Document.bates_start.split('-')[-1], 1), db.Integer) <= end_sequence,
                        # Other doc's end >= our start
                        db.func.cast(db.func.substr(Document.bates_end.split('-')[-1], 1), db.Integer) >= start_sequence
                    )
                )
            ).first()
            
            if overlap:
                flash(f'Bates number range conflicts with another document', 'error')
                return redirect(url_for('edit_bates', document_id=document_id))
            
            # Only re-stamp PDF if it's a PDF file and the Bates start has changed
            if document.file_extension.lower() == '.pdf' and document.bates_start != new_bates_start:
                bates_manager = BatesManager()
                try:
                    # Re-stamp the PDF with sequential Bates numbers starting from the new start
                    stamped_file_path = bates_manager._stamp_pdf_sequential(
                        document.local_path,
                        prefix,
                        start_sequence,
                        document.page_count
                    )
                    # Update the document path if stamping was successful
                    document.local_path = stamped_file_path
                except Exception as e:
                    flash(f'Error re-stamping PDF: {str(e)}. Database updated but PDF not re-stamped.', 'warning')
            
            # Update the document record
            old_bates_start = document.bates_start
            document.bates_number = new_bates_start
            document.bates_start = new_bates_start
            document.bates_end = new_bates_end
            document.bates_sequence = start_sequence
            
            db.session.commit()
            
            flash(f'Bates number range updated from {old_bates_start} to {new_bates_start}-{new_bates_end}', 'success')
            return redirect(url_for('view_case', case_id=document.case_id))
    
        return render_template('edit_bates.html', title="Edit Bates Number", 
                         document=document, case=case)

    @app.route('/prefix/<int:prefix_id>/edit', methods=['GET', 'POST'])
    def edit_prefix(prefix_id):
        from app.models.bates_prefix import BatesPrefix
        
        prefix = BatesPrefix.query.get_or_404(prefix_id)
        case_id = prefix.case_id
        
        if request.method == 'POST':
            new_prefix_value = request.form.get('prefix', '').strip()
            description = request.form.get('description', '')
            start_number = request.form.get('current_sequence', '1')
            
            if not new_prefix_value:
                flash('Prefix cannot be empty', 'error')
                return redirect(url_for('edit_prefix', prefix_id=prefix_id))
            
            try:
                start_number = int(start_number)
                if start_number < 1:
                    raise ValueError()
            except ValueError:
                flash('Sequence number must be a positive integer', 'error')
                return redirect(url_for('edit_prefix', prefix_id=prefix_id))
            
            # Check if the new prefix value conflicts with another prefix
            if new_prefix_value != prefix.prefix:
                existing = BatesPrefix.query.filter_by(
                    case_id=case_id, 
                    prefix=new_prefix_value
                ).first()
                
                if existing:
                    flash(f'Prefix "{new_prefix_value}" already exists for this case', 'error')
                    return redirect(url_for('edit_prefix', prefix_id=prefix_id))
            
            # Update the prefix
            prefix.prefix = new_prefix_value
            prefix.description = description
            prefix.current_sequence = start_number
            
            db.session.commit()
            
            flash('Prefix updated successfully', 'success')
            return redirect(url_for('case_prefixes', case_id=case_id))
        
        return render_template('edit_prefix.html', title="Edit Prefix", prefix=prefix)

    @app.route('/case/<int:case_id>/renumber-bates', methods=['GET', 'POST'])
    def renumber_case_bates(case_id):
        from app.models.case import Case
        from app.models.document import Document
        from app.utils.bates import BatesManager
        
        case = Case.query.get_or_404(case_id)
        
        if request.method == 'POST':
            start_number = request.form.get('start_number', '1')
            try:
                start_number = int(start_number)
            except ValueError:
                flash('Starting number must be an integer', 'error')
                return redirect(url_for('renumber_case_bates', case_id=case_id))
            
            # Get all documents in case, sorted by original bates sequence
            documents = Document.query.filter_by(case_id=case_id).order_by(Document.bates_sequence).all()
            
            # Renumber all documents
            bates_manager = BatesManager()
            for i, doc in enumerate(documents):
                new_sequence = start_number + i
                new_bates = f"{case.bates_prefix}-{str(new_sequence).zfill(6)}"
                
                # Update PDF if needed
                if doc.file_extension.lower() == '.pdf':
                    try:
                        stamped_path = bates_manager._stamp_pdf(doc.local_path, new_bates, doc.page_count)
                        doc.local_path = stamped_path
                    except Exception as e:
                        flash(f'Error re-stamping document {doc.original_filename}: {str(e)}', 'warning')
                
                # Update document record
                doc.bates_number = new_bates
                doc.bates_start = new_bates
                doc.bates_end = new_bates
                doc.bates_sequence = new_sequence
            
            # Update case sequence
            case.current_sequence = start_number + len(documents)
            db.session.commit()
            
            flash(f'Successfully renumbered {len(documents)} documents', 'success')
            return redirect(url_for('view_case', case_id=case_id))
        
        return render_template('renumber_bates.html', case=case)
    
    @app.route('/case/<int:case_id>/prefixes', methods=['GET', 'POST'])
    def case_prefixes(case_id):
        from app.models.case import Case
        from app.models.bates_prefix import BatesPrefix
        
        case = Case.query.get_or_404(case_id)
        
        if request.method == 'POST':
            prefix = request.form.get('prefix', '').strip()
            description = request.form.get('description', '')
            start_number = request.form.get('start_number', '1')
            is_default = 'is_default' in request.form
            
            if not prefix:
                flash('Prefix cannot be empty', 'error')
                return redirect(url_for('case_prefixes', case_id=case_id))
            
            try:
                start_number = int(start_number)
                if start_number < 1:
                    raise ValueError()
            except ValueError:
                flash('Starting number must be a positive integer', 'error')
                return redirect(url_for('case_prefixes', case_id=case_id))
            
            # Check if prefix already exists for this case
            existing = BatesPrefix.query.filter_by(case_id=case_id, prefix=prefix).first()
            if existing:
                flash(f'Prefix "{prefix}" already exists for this case', 'error')
                return redirect(url_for('case_prefixes', case_id=case_id))
            
            # If this is set as default, unset any existing default
            if is_default:
                current_default = BatesPrefix.query.filter_by(case_id=case_id, is_default=True).first()
                if current_default:
                    current_default.is_default = False
            
            # If this is the first prefix, make it default regardless
            first_prefix = BatesPrefix.query.filter_by(case_id=case_id).count() == 0
            
            # Create new prefix
            new_prefix = BatesPrefix(
                case_id=case_id,
                prefix=prefix,
                description=description,
                current_sequence=start_number,
                is_default=(is_default or first_prefix)
            )
            db.session.add(new_prefix)
            db.session.commit()
            
            flash(f'Prefix "{prefix}" added successfully', 'success')
            return redirect(url_for('case_prefixes', case_id=case_id))
        
        prefixes = BatesPrefix.query.filter_by(case_id=case_id).all()
        return render_template('case_prefixes.html', title="Manage Bates Prefixes", case=case, prefixes=prefixes)

    @app.route('/prefix/<int:prefix_id>/delete', methods=['POST'])
    def delete_prefix(prefix_id):
        from app.models.bates_prefix import BatesPrefix
        
        prefix = BatesPrefix.query.get_or_404(prefix_id)
        case_id = prefix.case_id
        
        # Don't allow deleting the default prefix
        if prefix.is_default:
            flash('Cannot delete the default prefix', 'error')
            return redirect(url_for('case_prefixes', case_id=case_id))
        
        db.session.delete(prefix)
        db.session.commit()
        
        flash(f'Prefix "{prefix.prefix}" deleted successfully', 'success')
        return redirect(url_for('case_prefixes', case_id=case_id))

    @app.route('/prefix/<int:prefix_id>/set-default', methods=['POST'])
    def set_default_prefix(prefix_id):
        from app.models.bates_prefix import BatesPrefix
        
        prefix = BatesPrefix.query.get_or_404(prefix_id)
        case_id = prefix.case_id
        
        # Unset current default
        current_default = BatesPrefix.query.filter_by(case_id=case_id, is_default=True).first()
        if current_default:
            current_default.is_default = False
        
        # Set new default
        prefix.is_default = True
        db.session.commit()
        
        flash(f'"{prefix.prefix}" is now the default prefix', 'success')
        return redirect(url_for('case_prefixes', case_id=case_id))

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
        from app.models.bates_prefix import BatesPrefix
        db.create_all()
        create_default_tags(app)
    
    return app