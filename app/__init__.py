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