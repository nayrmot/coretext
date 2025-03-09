import os
from app import db
from app.models.case import Case
from app.models.document import Document
from werkzeug.utils import secure_filename
import PyPDF2
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import io

class BatesManager:
    """Class to handle Bates numbering operations."""
    
    def __init__(self):
        pass
    
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
        
        # Generate the Bates number in the new format: Prefix-SequenceNumber
        bates_sequence = case.current_sequence
        bates_number = f"{case.bates_prefix}-{str(bates_sequence).zfill(6)}"
        
        # Create a unique filename to avoid overwriting
        base_name = os.path.splitext(filename)[0]
        unique_filename = f"{base_name}_{bates_number}{file_extension}"
        file_path = os.path.join(upload_folder, unique_filename)
        
        # Save the file
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Get page count for PDFs
        page_count = 1
        if file_extension.lower() == '.pdf':
            try:
                with open(file_path, 'rb') as f:
                    try:
                        pdf_reader = PyPDF2.PdfReader(f)
                        page_count = len(pdf_reader.pages)
                    except AttributeError:
                        pdf_reader = PyPDF2.PdfFileReader(f)
                        page_count = pdf_reader.getNumPages()
            except Exception as e:
                print(f"Error getting page count: {str(e)}")
        
        # Increment case sequence for next document
        case.current_sequence += 1
        db.session.commit()
        
        # For PDF files, add Bates stamps
        if file_extension.lower() == '.pdf':
            try:
                stamped_file_path = self._stamp_pdf(file_path, bates_number, page_count)
            except Exception as e:
                print(f"Error stamping PDF: {str(e)}")
                stamped_file_path = file_path  # Use original if stamping fails
        else:
            stamped_file_path = file_path  # For non-PDF files, use original path
        
        # Create document record
        document = Document(
            case_id=case_id,
            original_filename=filename,
            file_extension=file_extension,
            file_size=file_size,
            bates_number=bates_number,
            bates_sequence=bates_sequence,
            bates_start=bates_number,  # Use the same bates number for start
            bates_end=bates_number,    # Use the same bates number for end
            page_count=page_count,
            local_path=stamped_file_path
        )
        
        db.session.add(document)
        db.session.commit()
        
        return document
    
    def _stamp_pdf(self, pdf_path, bates_number, page_count=None, output_path=None):
        """
        Add Bates number to bottom right corner of each PDF page.
        
        Args:
            pdf_path: Path to the PDF file
            bates_number: Base Bates number to use
            page_count: Number of pages in the PDF (if already known)
            output_path: Path to save the stamped PDF
        """
        if output_path is None:
            output_path = f"{os.path.splitext(pdf_path)[0]}_BATES.pdf"
        
        # Open the original PDF
        with open(pdf_path, 'rb') as pdf_file:
            # Handle different PyPDF2 versions
            try:
                pdf_reader = PyPDF2.PdfReader(pdf_file)  # For newer PyPDF2 versions
                pdf_writer = PyPDF2.PdfWriter()
            except AttributeError:
                pdf_reader = PyPDF2.PdfFileReader(pdf_file)  # For older versions
                pdf_writer = PyPDF2.PdfFileWriter()
            
            # If page count not provided, calculate it
            if page_count is None:
                try:
                    page_count = len(pdf_reader.pages)
                except AttributeError:
                    page_count = pdf_reader.getNumPages()
            
            # Process each page
            for page_num in range(page_count):
                # Get the page (handle different PyPDF2 versions)
                try:
                    page = pdf_reader.pages[page_num]
                except AttributeError:
                    page = pdf_reader.getPage(page_num)
                
                # Use the same Bates number for all pages
                page_bates = bates_number
                
                packet = io.BytesIO()
                c = canvas.Canvas(packet, pagesize=letter)
                
                # Add Bates number at bottom right only
                c.setFont("Helvetica-Bold", 10)
                c.setFillColor(colors.black)
                c.drawString(5.5*inch, 0.75*inch, page_bates)
                
                c.save()
                
                # Move to the beginning of the StringIO buffer
                packet.seek(0)
                
                # Create a new PDF with the watermark
                try:
                    watermark = PyPDF2.PdfReader(packet)
                    watermark_page = watermark.pages[0]
                except AttributeError:
                    watermark = PyPDF2.PdfFileReader(packet)
                    watermark_page = watermark.getPage(0)
                
                # Merge the watermark with the page (handle different PyPDF2 versions)
                try:
                    page.merge_page(watermark_page)
                except AttributeError:
                    page.mergePage(watermark_page)
                
                # Add page to writer (handle different PyPDF2 versions)
                try:
                    pdf_writer.add_page(page)
                except AttributeError:
                    pdf_writer.addPage(page)
            
            # Save the result
            with open(output_path, 'wb') as output_file:
                pdf_writer.write(output_file)
        
        return output_path
    
    def search_documents(self, case_id=None, bates_number=None, filename=None, bates_range=None, tag_ids=None):
        """Search for documents based on criteria."""
        query = Document.query
        
        if case_id:
            query = query.filter_by(case_id=case_id)
        
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
        
        if bates_range and len(bates_range) == 2:
            start, end = bates_range
            query = query.filter(Document.bates_sequence.between(int(start), int(end)))
        
        # Filter by tags if tag_ids provided
        if tag_ids:
            from app.models.tag import DocumentTag
            query = query.join(DocumentTag).filter(DocumentTag.tag_id.in_(tag_ids))
        
        return query.all()
        
    def get_document_by_bates_number(self, bates_number):
        """
        Find a specific document by exact Bates number.
        
        Args:
            bates_number: The full Bates number to search for (e.g., "ABC-000123")
            
        Returns:
            Document information
        """
        # Find by exact Bates number
        document = Document.query.filter_by(bates_number=bates_number).first()
        
        if document:
            return {
                'document': document,
                'page_number': None,
                'is_page_specific': False
            }
        return None