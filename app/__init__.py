from flask import Flask, render_template, flash, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
import os

# Initialize extensions
db = SQLAlchemy()

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
    
    # Create database tables
    with app.app_context():
        # Import models here to avoid circular imports
        from app.models.case import Case
        from app.models.document import Document
        db.create_all()
    
    # Add this right before the "return app" line in create_app function

    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html', title='Page Not Found'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html', title='Server Error'), 500


    #View document
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


    return app