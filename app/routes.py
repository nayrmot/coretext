from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, send_file, session
from app import db
from app.models import Case, Document, Tag
from app.utils import BatesManager, GoogleDriveManager
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import tempfile
import json

main_bp = Blueprint('main', __name__)

# Helper function to check if request is from a mobile device
def is_mobile():
    user_agent = request.headers.get('User-Agent', '').lower()
    mobile_agents = ['iphone', 'ipod', 'android', 'blackberry', 'windows phone', 'mobile']
    return any(agent in user_agent for agent in mobile_agents)

@main_bp.context_processor
def inject_mobile_status():
    """Add mobile status to all templates"""
    return {'is_mobile': is_mobile()}

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
        
        # Google Drive folder configuration
        google_drive_enabled = request.form.get('google_drive_enabled', 'off') == 'on'
        gdrive_root_folder = request.form.get('gdrive_root_folder', '')
        gdrive_original_path = request.form.get('gdrive_original_path', 'Documents/Original')
        gdrive_bates_path = request.form.get('gdrive_bates_path', 'Documents/Bates Labeled')
        
        # If no Bates prefix provided, generate one from case name
        if not bates_prefix:
            words = case_name.split()
            bates_prefix = ''.join(word[0].upper() for word in words if word)
        
        # Create case in database
        case = Case(
            case_name=case_name,
            case_number=case_number,
            bates_prefix=bates_prefix,
            description=description,
            google_drive_enabled=google_drive_enabled,
            gdrive_root_folder=gdrive_root_folder,
            gdrive_original_path=gdrive_original_path,
            gdrive_bates_path=gdrive_bates_path
        )
        db.session.add(case)
        db.session.commit()
        
        # Create Google Drive folder structure if enabled
        if google_drive_enabled and gdrive_root_folder:
            try:
                credentials_path = current_app.config['GOOGLE_CLIENT_SECRETS_FILE']
                if os.path.exists(credentials_path):
                    drive_manager = GoogleDriveManager(credentials_path=credentials_path)
                    
                    # Create or ensure folder structure exists
                    folder_structure = drive_manager.create_or_verify_folder_structure(
                        root_folder=gdrive_root_folder,
                        original_path=gdrive_original_path,
                        bates_path=gdrive_bates_path,
                        case_name=case_name
                    )
                    
                    # Update case with folder information
                    case.drive_folder_id = folder_structure.get('case_folder', {}).get('id')
                    case.drive_folder_url = folder_structure.get('case_folder', {}).get('url')
                    case.drive_original_folder_id = folder_structure.get('original_folder', {}).get('id')
                    case.drive_bates_folder_id = folder_structure.get('bates_folder', {}).get('id')
                    
                    # Save document types if provided
                    doc_types = request.form.getlist('document_types')
                    if doc_types:
                        case.document_types = json.dumps(doc_types)
                        
                        # Create document type folders
                        for doc_type in doc_types:
                            drive_manager.create_folder(
                                doc_type, 
                                parent_id=case.drive_original_folder_id
                            )
                            drive_manager.create_folder(
                                doc_type, 
                                parent_id=case.drive_bates_folder_id
                            )
                    
                    db.session.commit()
                    flash(f"Case created successfully with Google Drive integration")
                else:
                    flash("Case created, but Google Drive credentials not found")
            except Exception as e:
                flash(f"Case created but Google Drive folders could not be created: {str(e)}")
        else:
            flash("Case created successfully without Google Drive integration")
        
        return redirect(url_for('main.case', case_id=case.id))
    
    return render_template('new_case.html', title='New Case')

@main_bp.route('/case/<int:case_id>')
def case(case_id):
    """View a specific case."""
    case = Case.query.get_or_404(case_id)
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Adjust per_page for mobile devices
    if is_mobile():
        per_page = 10
    
    # Filtering
    bates_number = request.args.get('bates_number', '')
    filename = request.args.get('filename', '')
    filetype = request.args.get('filetype', '')
    
    # Tag filtering
    tag_ids = request.args.getlist('tag_ids')
    
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
    
    # Filter by tags if requested
    if tag_ids:
        for tag_id in tag_ids:
            query = query.filter(Document.tags.any(id=tag_id))
    
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
    
    # Get case tags for filtering
    default_tags = Tag.query.filter_by(is_default=True).all()
    case_tags = Tag.query.filter_by(case_id=case_id).all()
    all_tags = default_tags + case_tags
    
    return render_template(
        'case.html', 
        title=case.case_name,
        case=case, 
        documents=documents, 
        pagination=pagination,
        all_tags=all_tags,
        selected_tag_ids=tag_ids
    )

@main_bp.route('/case/<int:case_id>/upload', methods=['GET', 'POST'])
def upload_document(case_id):
    """Upload a document to a case."""
    case = Case.query.get_or_404(case_id)
    
    # For GET requests, show the upload form
    if request.method == 'GET':
        # Parse document types if stored
        document_types = []
        if case.document_types:
            try:
                document_types = json.loads(case.document_types)
            except:
                document_types = []
                
        return render_template(
            'upload_document.html',
            title=f'Upload to {case.case_name}',
            case=case,
            document_types=document_types
        )
    
    # For POST requests, process the upload
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('main.upload_document', case_id=case_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('main.upload_document', case_id=case_id))
    
    if file:
        filename = secure_filename(file.filename)
        
        # Get document type if provided
        document_type = request.form.get('document_type', '')
        
        # Get starting Bates number if provided
        start_number = request.form.get('start_number')
        if start_number:
            try:
                start_number = int(start_number)
            except ValueError:
                flash('Invalid start number')
                return redirect(url_for('main.upload_document', case_id=case_id))
        
        # Save file temporarily
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, filename)
        file.save(file_path)
        
        # Process with Bates manager
        try:
            bates_manager = BatesManager()
            upload_folder = current_app.config['UPLOAD_FOLDER']
            
            # Prepare Google Drive parameters if enabled
            google_drive_params = None
            if case.google_drive_enabled:
                google_drive_params = {
                    'root_folder': case.gdrive_root_folder,
                    'original_path': case.gdrive_original_path,
                    'bates_path': case.gdrive_bates_path,
                    'document_type': document_type,
                    'folder_id': case.drive_folder_id,
                    'original_folder_id': case.drive_original_folder_id,
                    'bates_folder_id': case.drive_bates_folder_id,
                }
            
            # Process document
            result = bates_manager.process_document(
                case_id, 
                file_path, 
                filename, 
                upload_folder,
                start_number=start_number,
                document_type=document_type,
                google_drive_params=google_drive_params
            )
            
            flash(f"Document uploaded and assigned Bates numbers: {result['bates_start']} to {result['bates_end']}")
            else:
                flash(f"{len(results)} documents imported successfully")
        else:
            flash(f"Some documents could not be imported. {sum(1 for r in results if r['success'])} succeeded, {sum(1 for r in results if not r['success'])} failed.")
        
        return redirect(url_for('main.case', case_id=case_id))
    
    # List files in the folder
    try:
        credentials_path = current_app.config['GOOGLE_CLIENT_SECRETS_FILE']
        drive_manager = GoogleDriveManager(credentials_path=credentials_path)
        
        # Get folder contents
        contents = drive_manager.list_folder_contents(folder_id)
        
        # Get folder path/breadcrumbs
        if not parent_folders and folder_id != case.drive_folder_id:
            # Try to reconstruct path
            current_id = folder_id
            path = []
            
            while current_id and current_id != case.drive_folder_id:
                folder_info = drive_manager.get_folder_info(current_id)
                if folder_info:
                    path.insert(0, {
                        'id': current_id,
                        'name': folder_info.get('name', 'Unknown Folder')
                    })
                    parents = folder_info.get('parents', [])
                    current_id = parents[0] if parents else None
                else:
                    break
            
            # Add root folder
            if case.drive_folder_id:
                root_info = drive_manager.get_folder_info(case.drive_folder_id)
                parent_folders = [{
                    'id': case.drive_folder_id,
                    'name': root_info.get('name', case.case_name) if root_info else case.case_name
                }] + path[:-1]  # Exclude current folder from breadcrumbs
        
        # Parse document types for display
        document_types = []
        if case.document_types:
            try:
                document_types = json.loads(case.document_types)
            except:
                document_types = []
                
        return render_template(
            'browse_google_drive.html',
            title=f'Browse Google Drive for {case.case_name}',
            case=case,
            folder_id=folder_id,
            contents=contents,
            parent_folders=parent_folders,
            document_types=document_types
        )
    except Exception as e:
        flash(f"Error accessing Google Drive: {str(e)}", "error")
        return redirect(url_for('main.case', case_id=case_id))

@main_bp.route('/case/<int:case_id>/sync-with-drive', methods=['POST'])
def sync_with_drive(case_id):
    """Synchronize database with Google Drive."""
    case = Case.query.get_or_404(case_id)
    
    if not case.google_drive_enabled:
        flash("Google Drive is not enabled for this case", "error")
        return redirect(url_for('main.case', case_id=case_id))
    
    try:
        credentials_path = current_app.config['GOOGLE_CLIENT_SECRETS_FILE']
        drive_manager = GoogleDriveManager(credentials_path=credentials_path)
        bates_manager = BatesManager()
        
        # Check for new files in Google Drive
        bates_folder_id = case.drive_bates_folder_id
        if not bates_folder_id:
            flash("Bates labeled folder not found in Google Drive", "error")
            return redirect(url_for('main.case', case_id=case_id))
        
        # Get all files in the Bates folder and subfolders
        drive_files = drive_manager.list_all_files_in_folder(bates_folder_id, recursive=True)
        
        # Get existing documents in the database
        existing_docs = Document.query.filter_by(case_id=case_id).all()
        existing_file_ids = [doc.gdrive_file_id for doc in existing_docs if doc.gdrive_file_id]
        
        # Find new files
        new_files = [f for f in drive_files if f['id'] not in existing_file_ids]
        
        if not new_files:
            flash("No new files found in Google Drive", "info")
            return redirect(url_for('main.case', case_id=case_id))
        
        # Process new files
        imported_count = 0
        errors = []
        
        for file in new_files:
            try:
                # Extract Bates number from filename if possible
                filename = file['name']
                bates_number = None
                
                # Simple pattern matching for Bates numbers - might need refinement
                if case.bates_prefix and filename.startswith(case.bates_prefix):
                    # Try to extract Bates number from filename
                    bates_part = filename.split('.')[0]  # Remove extension
                    if bates_part and bates_part.startswith(case.bates_prefix):
                        bates_number = bates_part
                
                if not bates_number:
                    # Skip files without recognizable Bates numbers
                    errors.append(f"Could not extract Bates number from {filename}")
                    continue
                
                # Create document record
                document = Document(
                    case_id=case_id,
                    bates_number=bates_number,
                    original_filename=filename,
                    gdrive_file_id=file['id'],
                    gdrive_file_url=file.get('webViewLink', ''),
                    file_extension=os.path.splitext(filename)[1],
                    upload_date=datetime.utcnow()
                )
                
                # Try to parse Bates sequence number
                if case.bates_prefix and bates_number.startswith(case.bates_prefix):
                    num_part = bates_number[len(case.bates_prefix):]
                    try:
                        document.bates_sequence = int(num_part)
                    except ValueError:
                        pass
                
                db.session.add(document)
                imported_count += 1
            except Exception as e:
                errors.append(f"Error importing {file['name']}: {str(e)}")
        
        db.session.commit()
        
        if errors:
            flash(f"Imported {imported_count} files with {len(errors)} errors", "warning")
        else:
            flash(f"Successfully imported {imported_count} files from Google Drive", "success")
        
        return redirect(url_for('main.case', case_id=case_id))
    except Exception as e:
        flash(f"Error synchronizing with Google Drive: {str(e)}", "error")
        return redirect(url_for('main.case', case_id=case_id))

# Mobile-specific routes
@main_bp.route('/mobile/case/<int:case_id>')
def mobile_case_view(case_id):
    """Mobile-optimized view for a case."""
    if not is_mobile():
        return redirect(url_for('main.case', case_id=case_id))
    
    case = Case.query.get_or_404(case_id)
    
    # Simplified pagination with fewer results per page
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Smaller number for mobile
    
    # Simple filtering
    bates_number = request.args.get('bates_number', '')
    
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
    
    # Default sorting
    query = query.order_by(Document.bates_sequence.desc())
    
    # Execute query with pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    documents = pagination.items
    
    return render_template(
        'mobile/case.html', 
        title=case.case_name,
        case=case, 
        documents=documents, 
        pagination=pagination
    )

@main_bp.route('/mobile/document/<int:document_id>')
def mobile_document_details(document_id):
    """Mobile-optimized view for document details."""
    if not is_mobile():
        return redirect(url_for('main.document_details', document_id=document_id))
    
    document = Document.query.get_or_404(document_id)
    case = Case.query.get(document.case_id)
    
    # Update last accessed time
    document.last_accessed = datetime.utcnow()
    db.session.commit()
    
    return render_template(
        'mobile/document_details.html', 
        title=document.original_filename, 
        document=document, 
        case=case
    )

@main_bp.route('/mobile/case/<int:case_id>/upload', methods=['GET', 'POST'])
def mobile_upload_document(case_id):
    """Mobile-optimized view for document upload."""
    if not is_mobile():
        return redirect(url_for('main.upload_document', case_id=case_id))
    
    case = Case.query.get_or_404(case_id)
    
    # Handle POST same as regular upload_document
    if request.method == 'POST':
        return upload_document(case_id)
    
    # For GET, show mobile-optimized upload form
    document_types = []
    if case.document_types:
        try:
            document_types = json.loads(case.document_types)
        except:
            document_types = []
            
    return render_template(
        'mobile/upload_document.html',
        title=f'Upload to {case.case_name}',
        case=case,
        document_types=document_types
    )
)
            
            # Apply default tags if any
            document_id = result.get('document_id')
            if document_id:
                default_tag_ids = request.form.getlist('default_tags')
                if default_tag_ids:
                    document = Document.query.get(document_id)
                    for tag_id in default_tag_ids:
                        tag = Tag.query.get(tag_id)
                        if tag and tag not in document.tags:
                            document.tags.append(tag)
                    db.session.commit()
        except Exception as e:
            flash(f"Error processing document: {str(e)}")
        
        # Clean up temp file
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        
        return redirect(url_for('main.case', case_id=case_id))
    
    flash('Invalid file')
    return redirect(url_for('main.upload_document', case_id=case_id))

@main_bp.route('/case/<int:case_id>/settings', methods=['GET', 'POST'])
def case_settings(case_id):
    """Edit case settings including Google Drive configuration."""
    case = Case.query.get_or_404(case_id)
    
    if request.method == 'POST':
        # Update case details
        case.case_name = request.form.get('case_name', case.case_name)
        case.case_number = request.form.get('case_number', case.case_number)
        case.bates_prefix = request.form.get('bates_prefix', case.bates_prefix)
        case.description = request.form.get('description', case.description)
        
        # Update Google Drive settings
        case.google_drive_enabled = request.form.get('google_drive_enabled', 'off') == 'on'
        case.gdrive_root_folder = request.form.get('gdrive_root_folder', case.gdrive_root_folder)
        case.gdrive_original_path = request.form.get('gdrive_original_path', case.gdrive_original_path)
        case.gdrive_bates_path = request.form.get('gdrive_bates_path', case.gdrive_bates_path)
        
        # Update document types
        doc_types = request.form.getlist('document_types')
        if doc_types:
            # Get current document types
            current_types = []
            if case.document_types:
                try:
                    current_types = json.loads(case.document_types)
                except:
                    current_types = []
            
            # Find new types to create folders for
            new_types = [t for t in doc_types if t not in current_types]
            
            # Update the document types
            case.document_types = json.dumps(doc_types)
            
            # Create new document type folders if Google Drive is enabled
            if case.google_drive_enabled and new_types:
                try:
                    credentials_path = current_app.config['GOOGLE_CLIENT_SECRETS_FILE']
                    if os.path.exists(credentials_path):
                        drive_manager = GoogleDriveManager(credentials_path=credentials_path)
                        
                        for doc_type in new_types:
                            if case.drive_original_folder_id:
                                drive_manager.create_folder(doc_type, parent_id=case.drive_original_folder_id)
                            if case.drive_bates_folder_id:
                                drive_manager.create_folder(doc_type, parent_id=case.drive_bates_folder_id)
                except Exception as e:
                    flash(f"Could not create document type folders: {str(e)}")
        
        db.session.commit()
        flash('Case settings updated successfully')
        return redirect(url_for('main.case', case_id=case.id))
    
    # Parse document types for display
    document_types = []
    if case.document_types:
        try:
            document_types = json.loads(case.document_types)
        except:
            document_types = []
    
    return render_template(
        'case_settings.html',
        title=f'Settings for {case.case_name}',
        case=case,
        document_types=document_types
    )

@main_bp.route('/case/<int:case_id>/google-drive/test', methods=['POST'])
def test_google_drive(case_id):
    """Test Google Drive connectivity for a case."""
    case = Case.query.get_or_404(case_id)
    
    if not case.google_drive_enabled:
        return jsonify({
            'success': False,
            'message': 'Google Drive is not enabled for this case'
        })
    
    try:
        credentials_path = current_app.config['GOOGLE_CLIENT_SECRETS_FILE']
        if not os.path.exists(credentials_path):
            return jsonify({
                'success': False,
                'message': 'Google Drive credentials not found'
            })
        
        drive_manager = GoogleDriveManager(credentials_path=credentials_path)
        
        # Test connection and folder existence
        result = drive_manager.test_connection(
            root_folder=case.gdrive_root_folder,
            original_path=case.gdrive_original_path,
            bates_path=case.gdrive_bates_path
        )
        
        return jsonify({
            'success': True,
            'message': 'Google Drive connection successful',
            'details': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Google Drive test failed: {str(e)}'
        })

@main_bp.route('/document/<int:document_id>')
def document_details(document_id):
    """View document details."""
    document = Document.query.get_or_404(document_id)
    case = Case.query.get(document.case_id)
    
    # Update last accessed time
    document.last_accessed = datetime.utcnow()
    db.session.commit()
    
    return render_template(
        'document_details.html', 
        title=document.original_filename, 
        document=document, 
        case=case
    )

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
    elif document.gdrive_file_id:
        try:
            # Download from Google Drive
            credentials_path = current_app.config['GOOGLE_CLIENT_SECRETS_FILE']
            drive_manager = GoogleDriveManager(credentials_path=credentials_path)
            
            # Create temp directory for download
            temp_dir = tempfile.mkdtemp()
            local_path = os.path.join(temp_dir, f"{document.bates_number}{document.file_extension}")
            
            # Download file
            drive_manager.download_file(document.gdrive_file_id, local_path)
            
            @after_this_request
            def cleanup(response):
                # Clean up temporary file after sending
                if os.path.exists(local_path):
                    os.remove(local_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                return response
            
            return send_file(
                local_path,
                as_attachment=True,
                download_name=f"{document.bates_number}{document.file_extension}",
                mimetype='application/octet-stream'
            )
        except Exception as e:
            flash(f"Error downloading from Google Drive: {str(e)}")
            return redirect(url_for('main.document_details', document_id=document_id))
    else:
        flash("Document file not found.")
        return redirect(url_for('main.document_details', document_id=document_id))

@main_bp.route('/search', methods=['GET', 'POST'])
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
        
        # Adapt results for mobile if needed
        if is_mobile():
            # Potentially limit displayed fields or number of results
            pass
        
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

@main_bp.route('/tags')
def list_tags():
    """List all tags."""
    default_tags = Tag.query.filter_by(is_default=True).all()
    custom_tags = Tag.query.filter_by(is_default=False).order_by(Tag.case_id).all()
    
    return render_template(
        'tags.html', 
        title="Manage Tags", 
        default_tags=default_tags, 
        custom_tags=custom_tags
    )

@main_bp.route('/case/<int:case_id>/tags', methods=['GET', 'POST'])
def case_tags(case_id):
    """Manage tags for a case."""
    case = Case.query.get_or_404(case_id)
    
    if request.method == 'POST':
        tag_name = request.form.get('tag_name')
        tag_color = request.form.get('tag_color', '#6c757d')
        
        if not tag_name:
            flash('Tag name is required', 'error')
            return redirect(url_for('main.case_tags', case_id=case_id))
        
        # Check if tag already exists for this case
        existing_tag = Tag.query.filter_by(name=tag_name, case_id=case_id).first()
        if existing_tag:
            flash(f'Tag "{tag_name}" already exists for this case', 'error')
            return redirect(url_for('main.case_tags', case_id=case_id))
        
        # Create new tag
        tag = Tag(name=tag_name, color=tag_color, case_id=case_id)
        db.session.add(tag)
        db.session.commit()
        
        flash(f'Tag "{tag_name}" created successfully', 'success')
        return redirect(url_for('main.case_tags', case_id=case_id))
    
    # Get all available tags for this case (default + case-specific)
    default_tags = Tag.query.filter_by(is_default=True).all()
    case_tags = Tag.query.filter_by(case_id=case_id).all()
    
    return render_template(
        'case_tags.html', 
        title=f"Tags for {case.case_name}", 
        case=case, 
        default_tags=default_tags, 
        case_tags=case_tags
    )

@main_bp.route('/tag/<int:tag_id>/delete', methods=['POST'])
def delete_tag(tag_id):
    """Delete a tag."""
    tag = Tag.query.get_or_404(tag_id)
    
    # Don't allow deleting default tags
    if tag.is_default:
        flash('Cannot delete default tags', 'error')
        return redirect(url_for('main.list_tags'))
    
    case_id = tag.case_id
    
    # Delete the tag
    db.session.delete(tag)
    db.session.commit()
    
    flash(f'Tag "{tag.name}" deleted successfully', 'success')
    
    # Redirect back to case tags if from a case, otherwise to main tags page
    if case_id:
        return redirect(url_for('main.case_tags', case_id=case_id))
    else:
        return redirect(url_for('main.list_tags'))

@main_bp.route('/document/<int:document_id>/tags', methods=['GET', 'POST'])
def document_tags(document_id):
    """Manage tags for a document."""
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
        return redirect(url_for('main.document_details', document_id=document_id))
    
    # Get all available tags for this case (default + case-specific)
    default_tags = Tag.query.filter_by(is_default=True).all()
    case_tags = Tag.query.filter_by(case_id=document.case_id).all()
    all_tags = default_tags + case_tags
    
    # Get currently assigned tags
    current_tag_ids = [tag.id for tag in document.tags]
    
    return render_template(
        'document_tags.html', 
        title=f"Manage Tags for {document.original_filename}", 
        document=document, 
        case=case, 
        all_tags=all_tags, 
        current_tag_ids=current_tag_ids
    )

@main_bp.route('/case/<int:case_id>/browse-google-drive', methods=['GET', 'POST'])
def browse_google_drive(case_id):
    """Browse Google Drive files for a case."""
    case = Case.query.get_or_404(case_id)
    
    if not case.google_drive_enabled:
        flash("Google Drive is not enabled for this case", "error")
        return redirect(url_for('main.case', case_id=case_id))
    
    # Initialize parameters
    folder_id = request.args.get('folder_id') or case.drive_folder_id
    parent_folders = request.args.get('parents', '[]')
    
    try:
        parent_folders = json.loads(parent_folders)
    except:
        parent_folders = []
    
    if request.method == 'POST':
        # Process selected files
        selected_files = request.form.getlist('selected_files')
        if not selected_files:
            flash("No files selected", "error")
            return redirect(url_for('main.browse_google_drive', case_id=case_id, folder_id=folder_id, parents=json.dumps(parent_folders)))
        
        # Get document type if provided
        document_type = request.form.get('document_type', '')
        
        # Process each selected file
        results = []
        credentials_path = current_app.config['GOOGLE_CLIENT_SECRETS_FILE']
        drive_manager = GoogleDriveManager(credentials_path=credentials_path)
        bates_manager = BatesManager()
        
        for file_id in selected_files:
            try:
                # Download file to temp location
                file_info = drive_manager.get_file_info(file_id)
                filename = file_info.get('name', 'unknown.pdf')
                
                temp_dir = tempfile.mkdtemp()
                local_path = os.path.join(temp_dir, filename)
                
                drive_manager.download_file(file_id, local_path)
                
                # Process with Bates manager
                upload_folder = current_app.config['UPLOAD_FOLDER']
                
                google_drive_params = {
                    'root_folder': case.gdrive_root_folder,
                    'original_path': case.gdrive_original_path,
                    'bates_path': case.gdrive_bates_path,
                    'document_type': document_type,
                    'folder_id': case.drive_folder_id,
                    'original_folder_id': case.drive_original_folder_id,
                    'bates_folder_id': case.drive_bates_folder_id,
                    'source_file_id': file_id
                }
                
                result = bates_manager.process_document(
                    case_id, 
                    local_path, 
                    filename, 
                    upload_folder,
                    document_type=document_type,
                    google_drive_params=google_drive_params
                )
                
                results.append({
                    'filename': filename,
                    'success': True,
                    'bates_start': result['bates_start'],
                    'bates_end': result['bates_end']
                })
                
                # Clean up temp file
                if os.path.exists(local_path):
                    os.remove(local_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except Exception as e:
                results.append({
                    'filename': filename if 'filename' in locals() else 'Unknown file',
                    'success': False,
                    'error': str(e)
                })
        
        # Display results
        if all(r['success'] for r in results):
            if len(results) == 1:
                flash(f"Document imported and assigned Bates numbers: {results[0]['bates_start']} to {results[0]['bates_