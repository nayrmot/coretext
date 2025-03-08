from app import db
from app.models import Case, Document
import os
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter

class BatesManager:
    """Utility for managing Bates numbers in the CoreText system."""
    
    def __init__(self, page_separator="-"):
        """Initialize the Bates Manager."""
        self.page_separator = page_separator
    
    def get_next_bates_number(self, case_id, digits=6, start_number=None):
        """
        Get the next Bates number for a case.
        
        Args:
            case_id: The ID of the case
            digits: Number of digits to use for sequence formatting
            start_number: Optional starting number (for imports or existing documents)
            
        Returns:
            Tuple of (bates_number, sequence_number)
        """
        case = Case.query.get(case_id)
        if not case:
            raise ValueError(f"Case with ID {case_id} not found")
        
        # If a specific start number is provided, use it instead
        if start_number is not None:
            if start_number <= 0:
                raise ValueError("Start number must be positive")
            sequence_to_use = start_number
        else:
            sequence_to_use = case.current_sequence
        
        # Format the sequence number with leading zeros
        formatted_sequence = str(sequence_to_use).zfill(digits)
        bates_number = f"{case.bates_prefix}{formatted_sequence}"
        
        # Update the sequence for next use
        next_sequence = max(case.current_sequence, start_number or 0) + 1
        case.current_sequence = next_sequence
        db.session.commit()
        
        return bates_number, sequence_to_use
    
    def process_document(self, case_id, file_path, filename, upload_folder, google_drive_folder_id=None, start_number=None):
        """Process a document by assigning Bates number."""
        # Get file information
        file_name = filename or os.path.basename(file_path)
        file_extension = os.path.splitext(file_name)[1].lower()
        
        # Get next Bates number
        bates_number, sequence = self.get_next_bates_number(case_id, start_number=start_number)
        
        # Get page count for PDFs
        page_count = 1  # Default for non-PDF files
        if file_extension.lower() == '.pdf':
            with open(file_path, 'rb') as f:
                pdf = PdfReader(f)
                page_count = len(pdf.pages)
        
        # Generate start and end Bates numbers
        bates_start = f"{bates_number}{self.page_separator}001"
        bates_end = f"{bates_number}{self.page_separator}{str(page_count).zfill(3)}"
        
        # Calculate file size
        file_size = os.path.getsize(file_path)
        
        # For PDF files, add Bates stamps
        stamped_file_path = None
        if file_extension.lower() == '.pdf':
            # Create a path for the stamped file
            stamped_filename = f"{bates_number}{file_extension}"
            stamped_file_path = os.path.join(upload_folder, stamped_filename)
            self._stamp_pdf(file_path, bates_number, page_count, stamped_file_path)
        else:
            # For non-PDF files, just create a path in the upload folder
            stamped_filename = f"{bates_number}{file_extension}"
            stamped_file_path = os.path.join(upload_folder, stamped_filename)
            # Copy the file
            with open(file_path, 'rb') as src, open(stamped_file_path, 'wb') as dst:
                dst.write(src.read())
        
        # Create document record
        document = Document(
            case_id=case_id,
            original_filename=file_name,
            file_extension=file_extension,
            file_size=file_size,
            bates_number=bates_number,
            bates_sequence=sequence,
            bates_start=bates_start,
            bates_end=bates_end,
            page_count=page_count,
            local_path=stamped_file_path
        )
        
        # If Google Drive integration is active, handle the upload
        google_drive_id = None
        google_drive_path = None
        if google_drive_folder_id and hasattr(self, '_upload_to_drive'):
            google_drive_id, google_drive_path = self._upload_to_drive(
                stamped_file_path, 
                bates_number, 
                google_drive_folder_id
            )
            document.google_drive_id = google_drive_id
            document.google_drive_path = google_drive_path
        
        # Save the document to the database
        db.session.add(document)
        db.session.commit()
        
        return {
            'document_id': document.id,
            'bates_number': bates_number,
            'bates_start': bates_start,
            'bates_end': bates_end,
            'page_count': page_count,
            'local_path': stamped_file_path,
            'google_drive_id': google_drive_id,
            'google_drive_path': google_drive_path
        }
    
    def _stamp_pdf(self, pdf_path, bates_number, page_count=None, output_path=None):
        """
        Add Bates number to each page of a PDF.
        
        Args:
            pdf_path: Path to the PDF file
            bates_number: Base Bates number to use
            page_count: Number of pages in the PDF (if already known)
            output_path: Path to save the stamped PDF
            
        Returns:
            Path to the stamped PDF
        """
        if output_path is None:
            output_path = f"{os.path.splitext(pdf_path)[0]}_BATES.pdf"
        
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        # If page count not provided, calculate it
        if page_count is None:
            page_count = len(reader.pages)
        
        # Add Bates number to each page
        for i, page in enumerate(reader.pages):
            # Create page Bates number (e.g., PREFIX000001-001)
            page_bates = f"{bates_number}{self.page_separator}{str(i+1).zfill(3)}"
            
            # Create a new page with Bates stamp
            # In a real implementation, you would use a PDF library that can add text overlays
            # This is a simplified example using PyPDF2
            
            # Note: For a complete implementation, you would:
            # 1. Create a canvas overlay with ReportLab
            # 2. Draw the Bates number at desired positions (top-right, bottom-right, etc.)
            # 3. Merge the overlay with the original page
            
            writer.add_page(page)
            # In a real implementation, add watermark with: page.merge_page(watermark)
            
        # Save the stamped PDF
        with open(output_path, "wb") as output_file:
            writer.write(output_file)
            
        return output_path
    
    def search_documents(self, case_id=None, bates_number=None, filename=None, bates_range=None):
        """
        Search for documents based on various criteria.
        
        Args:
            case_id: Filter by specific case ID
            bates_number: Filter by Bates number (partial match)
            filename: Filter by filename (partial match)
            bates_range: Tuple of (start_bates, end_bates) to find documents in a range
            
        Returns:
            List of matching documents
        """
        query = Document.query
        
        if case_id:
            query = query.filter(Document.case_id == case_id)
            
        if bates_number:
            query = query.filter(
                db.or_(
                    Document.bates_number.ilike(f"%{bates_number}%"),
                    Document.bates_start.ilike(f"%{bates_number}%"),
                    Document.bates_end.ilike(f"%{bates_number}%")
                )
            )
            
        if filename:
            query = query.filter(Document.original_filename.ilike(f"%{filename}%"))
        
        if bates_range:
            start_bates, end_bates = bates_range
            # This query finds documents that overlap with the specified range
            # A document overlaps if its end is >= the search start AND its start <= the search end
            query = query.filter(Document.bates_end >= start_bates).filter(Document.bates_start <= end_bates)
        
        return query.all()
        
    def get_document_by_bates_number(self, bates_number):
        """
        Find a specific document by exact Bates number or a page within a document.
        
        Args:
            bates_number: The full Bates number to search for (e.g., "ABC000123" or "ABC000123-004")
            
        Returns:
            Document information and page number (if applicable)
        """
        # Check if this is a page-specific Bates number
        if self.page_separator in bates_number:
            base_bates, page_num = bates_number.split(self.page_separator, 1)
            page_num = int(page_num)
            
            # Find the document with this base Bates number
            document = Document.query.filter_by(bates_number=base_bates).first()
        else:
            # Find by exact base Bates number
            document = Document.query.filter_by(bates_number=bates_number).first()
            page_num = None
        
        if document:
            return {
                'document': document,
                'page_number': page_num,
                'is_page_specific': page_num is not None
            }
        return None
