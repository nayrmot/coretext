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
import logging
import io

class BatesManager:
    """Class to handle Bates numbering operations."""
    
    def __init__(self, page_separator="-"):
        self.page_separator = page_separator
        self.logger = logging.getLogger(__name__)

    def check_for_existing_bates(self, pdf_path):
        """
        Check if a PDF already has Bates numbers.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            tuple: (has_bates, detected_bates_numbers)
        """
        self.logger.info(f"Checking for existing Bates numbers in {pdf_path}")
        
        try:
            import re
            import PyPDF2
            
            # Common Bates number patterns
            bates_patterns = [
                r'[A-Z]+-\d{5,}',  # PREFIX-12345
                r'[A-Z]+\d{5,}',   # PREFIX12345
                r'[A-Z]+-[A-Z]+-\d{5,}',  # PREFIX-SUBPREFIX-12345
            ]
            
            compiled_patterns = [re.compile(pattern) for pattern in bates_patterns]
            
            with open(pdf_path, 'rb') as f:
                try:
                    pdf_reader = PyPDF2.PdfReader(f)
                    page_count = len(pdf_reader.pages)
                except AttributeError:
                    pdf_reader = PyPDF2.PdfFileReader(f)
                    page_count = pdf_reader.getNumPages()
            
                detected_bates = []
                
                # Check a sample of pages (first, last, and a middle page if applicable)
                pages_to_check = [0]  # Always check first page
                if page_count > 1:
                    pages_to_check.append(page_count - 1)  # Last page
                if page_count > 2:
                    pages_to_check.append(page_count // 2)  # Middle page
                
                for page_num in pages_to_check:
                    try:
                        # Extract text
                        try:
                            page = pdf_reader.pages[page_num]
                            text = page.extract_text()
                        except AttributeError:
                            page = pdf_reader.getPage(page_num)
                            text = page.extractText()
                        
                        # Look for Bates patterns
                        for pattern in compiled_patterns:
                            matches = pattern.findall(text)
                            detected_bates.extend(matches)
                        
                    except Exception as e:
                        self.logger.warning(f"Error extracting text from page {page_num}: {str(e)}")
                
                # Remove duplicates
                detected_bates = list(set(detected_bates))
                
                has_bates = len(detected_bates) > 0
                
                if has_bates:
                    self.logger.info(f"Detected existing Bates numbers: {', '.join(detected_bates)}")
                else:
                    self.logger.info("No existing Bates numbers detected")
                    
                return has_bates, detected_bates
                
        except Exception as e:
            self.logger.error(f"Error checking for existing Bates numbers: {str(e)}", exc_info=True)
            return False, []
    
    def _stamp_pdf(self, pdf_path, bates_prefix, page_count=None, start_sequence=None, output_path=None):
        """
        Add Bates number to bottom right corner of each PDF page.
        """
        if output_path is None:
            output_path = f"{os.path.splitext(pdf_path)[0]}_BATES.pdf"
        
        self.logger.info(f"Starting PDF stamping: prefix={bates_prefix}, start_sequence={start_sequence}, pages={page_count}")
        
        try:
            # Open the original PDF
            with open(pdf_path, 'rb') as pdf_file:
                # Handle different PyPDF2 versions
                try:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    pdf_writer = PyPDF2.PdfWriter()
                    self.logger.debug("Using PyPDF2 PdfReader")
                except AttributeError:
                    pdf_reader = PyPDF2.PdfFileReader(pdf_file)
                    pdf_writer = PyPDF2.PdfFileWriter()
                    self.logger.debug("Using PyPDF2 PdfFileReader")
                
                # If page count not provided, calculate it
                actual_page_count = 0
                try:
                    actual_page_count = len(pdf_reader.pages)
                except AttributeError:
                    actual_page_count = pdf_reader.getNumPages()
                
                self.logger.info(f"PDF has {actual_page_count} pages")
                
                if page_count is None:
                    page_count = actual_page_count
                
                # Process each page
                for page_num in range(page_count):
                    # Get the page (handle different PyPDF2 versions)
                    try:
                        page = pdf_reader.pages[page_num]
                    except AttributeError:
                        page = pdf_reader.getPage(page_num)
                    
                    # Generate the Bates number for this page
                    if start_sequence is not None:
                        # Sequential numbering mode
                        current_sequence = start_sequence + page_num
                        page_bates = f"{bates_prefix}-{str(current_sequence).zfill(6)}"
                    else:
                        # Original mode
                        page_bates = f"{bates_prefix}{self.page_separator}{str(page_num+1).zfill(3)}"
                    
                    self.logger.debug(f"Stamping page {page_num+1} with Bates number: {page_bates}")
                    
                    # Create a watermark with the Bates number
                    packet = io.BytesIO()
                    c = canvas.Canvas(packet, pagesize=letter)
                    
                    # Add Bates number at bottom right
                    c.setFont("Helvetica-Bold", 10)
                    c.setFillColor(colors.black)
                    c.drawString(5.5*inch, 0.75*inch, page_bates)
                    
                    c.save()
                    packet.seek(0)
                    
                    # Create a new PDF with the watermark
                    try:
                        watermark = PyPDF2.PdfReader(packet)
                        watermark_page = watermark.pages[0]
                    except AttributeError:
                        watermark = PyPDF2.PdfFileReader(packet)
                        watermark_page = watermark.getPage(0)
                    
                    # Merge the watermark with the page
                    try:
                        page.merge_page(watermark_page)
                        self.logger.debug(f"Page {page_num+1} merged successfully")
                    except AttributeError:
                        page.mergePage(watermark_page)
                        self.logger.debug(f"Page {page_num+1} merged successfully (legacy)")
                    except Exception as e:
                        self.logger.error(f"Error merging page {page_num+1}: {str(e)}")
                    
                    # Add page to writer
                    try:
                        pdf_writer.add_page(page)
                    except AttributeError:
                        pdf_writer.addPage(page)
                
                # Save the result
                try:
                    with open(output_path, 'wb') as output_file:
                        pdf_writer.write(output_file)
                    self.logger.info(f"Stamped PDF saved to {output_path}")
                except Exception as e:
                    self.logger.error(f"Error saving stamped PDF: {str(e)}")
                    return pdf_path  # Return original path on error
            
            return output_path
        except Exception as e:
            import traceback
            self.logger.error(f"PDF stamping failed: {str(e)}")
            self.logger.error(traceback.format_exc())
            return pdf_path  # Return original path on error

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
        try:
            # Get the case
            case = Case.query.get(case_id)
            if not case:
                self.logger.error(f"Case with ID {case_id} not found")
                raise ValueError(f"Case with ID {case_id} not found")
            
            # Get the default Bates prefix
            from app.models.bates_prefix import BatesPrefix
            prefix_obj = BatesPrefix.query.filter_by(case_id=case_id, is_default=True).first()
            if not prefix_obj:
                self.logger.error(f"No default Bates prefix found for case ID {case_id}")
                raise ValueError(f"No default Bates prefix found for case ID {case_id}")
            
            # Get file information
            filename = secure_filename(file.filename)
            file_extension = os.path.splitext(filename)[1].lower()
            
            self.logger.info(f"Processing document: {filename} with prefix {prefix_obj.prefix}")
            
            # Get page count for PDFs
            page_count = 1
            temp_path = os.path.join(upload_folder, "temp_file" + file_extension)
            file.save(temp_path)
            
            if file_extension.lower() == '.pdf':
                try:
                    with open(temp_path, 'rb') as f:
                        try:
                            pdf_reader = PyPDF2.PdfReader(f)
                            page_count = len(pdf_reader.pages)
                            is_encrypted = getattr(pdf_reader, 'is_encrypted', False)
                            self.logger.info(f"PDF info: Encrypted={is_encrypted}, Pages={page_count}")
                        except AttributeError:
                            pdf_reader = PyPDF2.PdfFileReader(f)
                            page_count = pdf_reader.getNumPages()
                            self.logger.info(f"PDF info: Encrypted={pdf_reader.isEncrypted}, Pages={page_count}")
                except Exception as e:
                    self.logger.error(f"Error getting page count: {str(e)}", exc_info=True)
            
            # Generate the Bates number range
            start_sequence = prefix_obj.current_sequence
            end_sequence = start_sequence + page_count - 1
            
            bates_start = f"{prefix_obj.prefix}-{str(start_sequence).zfill(6)}"
            bates_end = f"{prefix_obj.prefix}-{str(end_sequence).zfill(6)}"
            
            self.logger.info(f"Generated Bates range: {bates_start} to {bates_end} for {page_count} pages")
            
            # Create a unique filename to avoid overwriting
            base_name = os.path.splitext(filename)[0]
            unique_filename = f"{base_name}_{bates_start}_to_{bates_end}{file_extension}"
            file_path = os.path.join(upload_folder, unique_filename)
            
            # Move the temp file to the final location
            import shutil
            shutil.copy2(temp_path, file_path)
            
            # For PDF files, add Bates stamps with sequential numbering
            if file_extension.lower() == '.pdf':
                try:
                    self.logger.info(f"Stamping PDF with sequential Bates numbers, starting at {start_sequence}")
                    stamped_file_path = self._stamp_pdf_sequential(
                        file_path,
                        prefix_obj.prefix,
                        start_sequence,
                        page_count
                    )
                    
                    # Verify stamping worked by checking file size
                    orig_size = os.path.getsize(file_path)
                    stamped_size = os.path.getsize(stamped_file_path)
                    
                    if stamped_size <= orig_size + 100:  # If file size barely changed
                        self.logger.warning("Stamping may have failed (no significant file size change)")
                        self.logger.info("Original size: {}, Stamped size: {}".format(orig_size, stamped_size))
                except Exception as e:
                    self.logger.error(f"Error stamping PDF: {str(e)}", exc_info=True)
                    stamped_file_path = file_path  # Use original if stamping fails
            else:
                self.logger.info(f"Non-PDF file, skipping Bates stamping")
                stamped_file_path = file_path  # For non-PDF files, use original path
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                self.logger.debug("Temporary file removed")
            
            # Get file size
            file_size = os.path.getsize(stamped_file_path)
            
            # Update prefix current sequence
            old_sequence = prefix_obj.current_sequence
            prefix_obj.current_sequence = end_sequence + 1
            self.logger.info(f"Updated prefix sequence from {old_sequence} to {prefix_obj.current_sequence}")
            
            # Create document record
            document = Document(
                case_id=case_id,
                original_filename=filename,
                file_extension=file_extension,
                file_size=file_size,
                bates_number=bates_start,
                bates_sequence=start_sequence,
                bates_start=bates_start,
                bates_end=bates_end,
                page_count=page_count,
                local_path=stamped_file_path
            )
            
            self.logger.info(f"Creating document record: {bates_start} to {bates_end}")
            db.session.add(document)
            db.session.commit()
            
            return document
        except Exception as e:
            self.logger.error(f"Error processing document: {str(e)}", exc_info=True)
            raise
    
    def process_document_with_prefix(self, case_id, file, upload_folder, prefix, force_relabel=False):
        try:
            # Get the case
            case = Case.query.get(case_id)
            if not case:
                self.logger.error(f"Case with ID {case_id} not found")
                raise ValueError(f"Case with ID {case_id} not found")
            
            # Get file information
            filename = secure_filename(file.filename)
            file_extension = os.path.splitext(filename)[1].lower()
            
            self.logger.info(f"Processing document: {filename} with prefix {prefix.prefix}")
            
            # Save file to get page count first
            temp_path = os.path.join(upload_folder, "temp_" + filename)
            file.save(temp_path)
            
            # Check for existing Bates numbers if it's a PDF
            existing_bates_detected = False
            existing_bates_numbers = []
            
            if file_extension.lower() == '.pdf':
                existing_bates_detected, existing_bates_numbers = self.check_for_existing_bates(temp_path)
            
            # If Bates numbers detected and not forcing relabel, skip Bates stamping
            skip_stamping = existing_bates_detected and not force_relabel
            
            # Get page count for PDFs
            page_count = 1
            if file_extension.lower() == '.pdf':
                try:
                    with open(temp_path, 'rb') as f:
                        try:
                            pdf_reader = PyPDF2.PdfReader(f)
                            page_count = len(pdf_reader.pages)
                            is_encrypted = getattr(pdf_reader, 'is_encrypted', False)
                            self.logger.info(f"PDF info: Encrypted={is_encrypted}, Pages={page_count}")
                        except AttributeError:
                            pdf_reader = PyPDF2.PdfFileReader(f)
                            page_count = pdf_reader.getNumPages()
                            self.logger.info(f"PDF info: Encrypted={pdf_reader.isEncrypted}, Pages={page_count}")
                except Exception as e:
                    self.logger.error(f"Error getting page count: {str(e)}", exc_info=True)
            
            # Generate the Bates number range
            start_sequence = prefix.current_sequence
            end_sequence = start_sequence + page_count - 1
            
            bates_start = f"{prefix.prefix}-{str(start_sequence).zfill(6)}"
            bates_end = f"{prefix.prefix}-{str(end_sequence).zfill(6)}"
            
            self.logger.info(f"Generated Bates range: {bates_start} to {bates_end} for {page_count} pages")
            
            # Create a unique filename to avoid overwriting
            base_name = os.path.splitext(filename)[0]
            unique_filename = f"{base_name}_{bates_start}_to_{bates_end}{file_extension}"
            file_path = os.path.join(upload_folder, unique_filename)  # Define file_path here
            
            # Move the temp file to the final location
            import shutil
            shutil.copy2(temp_path, file_path)
            
            # For PDF files, add Bates stamps with sequential numbering only if not skipping
            if file_extension.lower() == '.pdf' and not skip_stamping:
                try:
                    self.logger.info(f"Stamping PDF with sequential Bates numbers, starting at {start_sequence}")
                    stamped_file_path = self._stamp_pdf_sequential(
                        file_path,
                        prefix.prefix,
                        start_sequence,
                        page_count
                    )
                    
                    # Verify stamping worked by checking file size
                    orig_size = os.path.getsize(file_path)
                    stamped_size = os.path.getsize(stamped_file_path)
                    
                    if stamped_size <= orig_size + 100:  # If file size barely changed
                        self.logger.warning("Stamping may have failed (no significant file size change)")
                        self.logger.info(f"Original size: {orig_size}, Stamped size: {stamped_size}")
                except Exception as e:
                    self.logger.error(f"Error stamping PDF: {str(e)}", exc_info=True)
                    stamped_file_path = file_path  # Use original if stamping fails
            else:
                if skip_stamping:
                    self.logger.info(f"Skipping Bates stamping due to existing Bates numbers: {', '.join(existing_bates_numbers)}")
                else:
                    self.logger.info(f"Skipping Bates stamping for non-PDF file")
                stamped_file_path = file_path  # Use original path
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                self.logger.debug("Temporary file removed")
            
            # Get file size
            file_size = os.path.getsize(stamped_file_path)
            
            # Create document record
            document = Document(
                case_id=case_id,
                original_filename=filename,
                file_extension=file_extension,
                file_size=file_size,
                bates_number=bates_start,
                bates_sequence=start_sequence,
                bates_start=bates_start,
                bates_end=bates_end,
                page_count=page_count,
                local_path=stamped_file_path,
                existing_bates=existing_bates_detected and not force_relabel,
                bates_note=', '.join(existing_bates_numbers) if existing_bates_detected else None
            )
            
            self.logger.info(f"Creating document record: {bates_start} to {bates_end}")
            db.session.add(document)
            
            # Update prefix sequence for next document
            old_sequence = prefix.current_sequence
            prefix.current_sequence = end_sequence + 1
            self.logger.info(f"Updated prefix sequence from {old_sequence} to {prefix.current_sequence}")
            db.session.commit()
            
            return document
        except Exception as e:
            self.logger.error(f"Error processing document with prefix: {str(e)}", exc_info=True)
            raise

    def _stamp_pdf_sequential(self, pdf_path, prefix, start_sequence, page_count, output_path=None):
        """
        Add sequential Bates numbers to each page of a PDF.
        
        Args:
            pdf_path: Path to the PDF file
            prefix: Bates prefix to use (e.g., "Johnson-Pltf")
            start_sequence: Starting sequence number
            page_count: Number of pages in the PDF
            output_path: Path to save the stamped PDF
        """
        if output_path is None:
            output_path = f"{os.path.splitext(pdf_path)[0]}_BATES.pdf"
        
        self.logger.info(f"Starting sequential PDF stamping: prefix={prefix}, start_sequence={start_sequence}, pages={page_count}")
        
        try:
            # Open the original PDF
            with open(pdf_path, 'rb') as pdf_file:
                # Handle different PyPDF2 versions
                try:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)  # For newer PyPDF2 versions
                    pdf_writer = PyPDF2.PdfWriter()
                    self.logger.debug("Using PyPDF2 PdfReader")
                except AttributeError:
                    pdf_reader = PyPDF2.PdfFileReader(pdf_file)  # For older versions
                    pdf_writer = PyPDF2.PdfFileWriter()
                    self.logger.debug("Using PyPDF2 PdfFileReader")
                
                # Get actual page count
                actual_page_count = 0
                try:
                    actual_page_count = len(pdf_reader.pages)
                except AttributeError:
                    actual_page_count = pdf_reader.getNumPages()
                
                self.logger.info(f"PDF has {actual_page_count} actual pages")
                
                # Use the smaller of the two page counts to avoid issues
                page_count = min(page_count, actual_page_count)
                
                # Process each page with sequential Bates numbers
                for page_num in range(page_count):
                    # Get the page (handle different PyPDF2 versions)
                    try:
                        page = pdf_reader.pages[page_num]
                    except AttributeError:
                        page = pdf_reader.getPage(page_num)
                    
                    # Generate the sequential Bates number for this page
                    current_sequence = start_sequence + page_num
                    page_bates = f"{prefix}-{str(current_sequence).zfill(6)}"
                    
                    self.logger.debug(f"Stamping page {page_num+1} with Bates number: {page_bates}")
                    
                    packet = io.BytesIO()
                    c = canvas.Canvas(packet, pagesize=letter)
                    
                    # Add Bates number at bottom right
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
                        self.logger.debug(f"Page {page_num+1} merged successfully")
                    except AttributeError:
                        page.mergePage(watermark_page)
                        self.logger.debug(f"Page {page_num+1} merged successfully (legacy)")
                    except Exception as e:
                        self.logger.error(f"Error merging page {page_num+1}: {str(e)}")
                    
                    # Add page to writer (handle different PyPDF2 versions)
                    try:
                        pdf_writer.add_page(page)
                    except AttributeError:
                        pdf_writer.addPage(page)
                
                # Save the result
                try:
                    with open(output_path, 'wb') as output_file:
                        pdf_writer.write(output_file)
                    self.logger.info(f"Stamped PDF saved to {output_path}")
                except Exception as e:
                    self.logger.error(f"Error saving stamped PDF: {str(e)}")
                    return pdf_path  # Return original path on error
                
                return output_path
        except Exception as e:
            import traceback
            self.logger.error(f"Sequential PDF stamping failed: {str(e)}")
            self.logger.error(traceback.format_exc())
            return pdf_path  # Return original path on error
  
    def search_documents(self, case_id=None, bates_number=None, filename=None, bates_range=None, tag_ids=None):
        """Search for documents based on criteria."""
        query = Document.query
        
        if case_id:
            query = query.filter_by(case_id=case_id)
        
        if bates_number:
            # Handle both single and double hyphen cases
            search_term = bates_number.strip('-')  # Remove trailing hyphens for searching
            
            query = query.filter(
                db.or_(
                    Document.bates_number.ilike(f'%{search_term}%'),
                    Document.bates_start.ilike(f'%{search_term}%'),
                    Document.bates_end.ilike(f'%{search_term}%')
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