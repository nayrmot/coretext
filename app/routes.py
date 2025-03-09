from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, send_file
from app import db
from app.models import Case, Document
from app.utils import BatesManager, GoogleDriveManager
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import tempfile

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Home page showing a list of cases."""
    cases = Case.query.all()
    return render_template('index.html', title='Home', cases=cases)

@main_bp.route('/case/new', methods=['GET', 'POST'])
def new_case():
    """Create a new case."""
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
        
        # Create Google Drive folder structure
        try:
            credentials_path = current_app.config['GOOGLE_CLIENT_SECRETS_FILE']
            if os.path.exists(credentials_path):
                drive_manager = GoogleDriveManager(credentials_path=credentials_path)
                folder_structure = drive_manager.create_folder_structure(case_name)
                
                # Update case with folder information
                case.drive_folder_id = folder_structure['case_folder']['id']
                case.drive_folder_url = folder_structure['case_folder']['url']
                db.session.commit()
                
                flash(f"Case created successfully with Google Drive folder: {folder_structure['case_folder']['url']}")
            else:
                flash("Case created, but Google Drive integration is not configured.")
        except Exception as e:
            flash(f"Case created but Google Drive folders could not be created: {str(e)}")
        
        return redirect(url_for('main.case', case_id=case.id))
    
    return render_template('new_case.html', title='New Case')

@main_bp.route('/case/<int:case_id>')
def case(case_id):
    """View a specific case."""
    case = Case.query.get_or_404(case_id)
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Filtering
    bates_number = request.args.get('bates_number', '')
    filename = request.args.get('filename', '')
    filetype = request.args.get('filetype', '')
    
    # Build query
    query = Document.query.filter_by(case_id=case_id)
    
    if bates_number:
        query = query.filter(
            db.or_(
                Document.bates_number.ilike(f'%{bates_number}%'),
                Document.bates_start.ilike(f'%{bates_number}%'),
                Document.bates_end.ilike(f'%{bates_number}%')
            )
        )
    
    if filename:
        query = query.filter(Document.original_filename.ilike(f'%{filename}%'))
    
    if filetype:
        query = query.filter(Document.file_extension == filetype)
    
    # Sorting
    sort = request.args.get('sort', 'bates_desc')
    if sort == 'bates_asc':
        query = query.order_by(Document.bates_sequence.asc())
    elif sort == 'bates_desc':
        query = query.order_by(Document.bates_sequence.desc())
    elif sort == 'date_asc':
        query = query.order_by(Document.upload_date.asc())
    elif sort == 'date_desc':
        query = query.order_by(Document.upload_date.desc())
    elif sort == 'name_asc':
        query = query.order_by(Document.original_filename.asc())
    elif sort == 'name_desc':
        query = query.order_by(Document.original_filename.desc())
    else:
        query = query.order_by(Document.bates_sequence.desc())
    
    # Execute query with pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    documents = pagination.items
    
    return render_template(
        'case.html', 
        title=case.case_name,
        case=case, 
        documents=documents, 
        pagination=pagination
    )

@main_bp.route('/case/<int:case_id>/upload', methods=['POST'])
def upload_document(case_id):
    """Upload a document to a case."""
    case = Case.query.get_or_404(case_id)
    
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('main.case', case_id=case_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('main.case', case_id=case_id))
    
    if file:
        filename = secure_filename(file.filename)
        
        # Get starting Bates number if provided
        start_number = request.form.get('start_number')
        if start_number:
            try:
                start_number = int(start_number)
            except ValueError:
                flash('Invalid start number')
                return redirect(url_for('main.case', case_id=case_id))
        
        # Save file temporarily
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, filename)
        file.save(file_path)
        
        # Process with Bates manager
        try:
            bates_manager = BatesManager()
            upload_folder = current_app.config['UPLOAD_FOLDER']
            
            # Get Google Drive folder ID if available
            google_drive_folder_id = case.drive_folder_id
            
            # Process document
            result = bates_manager.process_document(
                case_id, 
                file_path, 
                filename, 
                upload_folder,
                google_drive_folder_id, 
                start_number
            )
            
            flash(f"Document uploaded and assigned Bates numbers: {result['bates_start']} to {result['bates_end']}")
        except Exception as e:
            flash(f"Error processing document: {str(e)}")
        
        # Clean up temp file
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        
    return redirect(url_for('main.case', case_id=case_id))

@main_bp.route('/document/<int:document_id>')
def document_details(document_id):
    """View document details."""
    document = Document.query.get_or_404(document_id)
    case = Case.query.get(document.case_id)
    
    # Update last accessed time
    document.last_accessed = datetime.utcnow()
    db.session.commit()
    
    return render_template('document_details.html', title=document.original_filename, document=document, case=case)

@main_bp.route('/document/<int:document_id>/download')
def download_document(document_id):
    """Download a document."""
    document = Document.query.get_or_404(document_id)
    
    if document.local_path and os.path.exists(document.local_path):
        return send_file(
            document.local_path,
            as_attachment=True,
            download_name=f"{document.bates_number}{document.file_extension}",
            mimetype='application/octet-stream'
        )
    else:
        flash("Document file not found.")
        return redirect(url_for('main.document_details', document_id=document_id))

@main_bp.route('/search', methods=['GET', 'POST'])
def search():
    def search():
    """Search for documents."""
    if request.method == 'POST':
        bates_number = request.form.get('bates_number', '')
        case_id = request.form.get('case_id')
        filename = request.form.get('filename', '')
        tag_ids = request.form.getlist('tag_ids')  # Get selected tag IDs
        
        # Check for Bates range search
        bates_range = None
        bates_start = request.form.get('bates_start', '')
        bates_end = request.form.get('bates_end', '')
        if bates_start and bates_end:
            bates_range = (bates_start, bates_end)
        
        if case_id:
            try:
                case_id = int(case_id)
            except ValueError:
                case_id = None
        
        bates_manager = BatesManager()
        results = bates_manager.search_documents(
            case_id=case_id,
            bates_number=bates_number,
            filename=filename,
            bates_range=bates_range,
            tag_ids=tag_ids  # Pass tag IDs to search function
        )
        
        return render_template('search_results.html', results=results, title='Search Results')
    
    cases = Case.query.all()
    default_tags = Tag.query.filter_by(is_default=True).all()
    
    return render_template('search.html', cases=cases, default_tags=default_tags, title='Search Documents')
    

@main_bp.route('/bates/<string:bates_number>')
def bates_lookup(bates_number):
    """Look up a document by Bates number."""
    bates_manager = BatesManager()
    result = bates_manager.get_document_by_bates_number(bates_number)
    
    if not result:
        flash(f"Document with Bates number {bates_number} not found")
        return redirect(url_for('main.search'))
    
    document = result['document']
    
    # If it's a page-specific Bates number, include the page information
    page_number = result.get('page_number')
    
    return render_template(
        'document_details.html',
        document=document,
        case=Case.query.get(document.case_id),
        page_number=page_number,
        title=f"Bates Number {bates_number}"
    )

@app.route('/tags')
def list_tags():
    default_tags = Tag.query.filter_by(is_default=True).all()
    custom_tags = Tag.query.filter_by(is_default=False).order_by(Tag.case_id).all()
    return render_template('tags.html', title="Manage Tags", 
                           default_tags=default_tags, 
                           custom_tags=custom_tags)

@app.route('/case/<int:case_id>/tags', methods=['GET', 'POST'])
def case_tags(case_id):
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
