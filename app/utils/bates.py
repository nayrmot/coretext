# File: app/utils/bates.py
import os
from app import db
from app.models.case import Case
from app.models.document import Document
from werkzeug.utils import secure_filename
import PyPDF2

class BatesManager:
    """Class to handle Bates numbering operations."""
    
    def __init__(self, page_separator="-"):
        self.page_separator = page_separator
    
    def process_document(self, case_id, file, upload_folder):
        """
        Process a document by assigning a Bates number and saving it.
        
        Args:
            case_id: The ID of the case
            file: The uploaded file object
            upload_folder: The directory to save files
            
        Returns:
            Document object with Bates information
        """
        # Get the case
        case = Case.query.get(case_id)
        if not case:
            raise ValueError(f"Case with ID {case_id} not found")
        
        # Get file information
        filename = secure_filename(file.filename)
        file_extension = os.path.splitext(filename)[1].lower()
        
        # Save the file
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Get page count for PDFs
        page_count = 1
        if file_extension == '.pdf':
            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfFileReader(pdf_file)
                page_count = pdf_reader.numPages
        
        # Get next Bates number
        bates_sequence = case.current_sequence
        bates_number = f"{case.bates_prefix}{str(bates_sequence).zfill(6)}"
        
        # Generate start and end Bates numbers
        bates_start = f"{bates_number}{self.page_separator}001"
        bates_end = f"{bates_number}{self.page_separator}{str(page_count).zfill(3)}"
        
        # Increment case sequence
        case.current_sequence += 1
        db.session.commit()
        
        # Create document record
        document = Document(
            case_id=case_id,
            original_filename=filename,
            file_extension=file_extension,
            file_size=file_size,
            bates_number=bates_number,
            bates_sequence=bates_sequence,
            bates_start=bates_start,
            bates_end=bates_end,
            page_count=page_count,
            local_path=file_path
        )
        
        db.session.add(document)
        db.session.commit()
        
        return document