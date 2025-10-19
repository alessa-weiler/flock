# Test Fixtures

This directory contains sample files for testing the Knowledge Platform document processing functionality.

## Available Test Files

### Text Files
- **sample.txt** - Plain text file with UTF-8 encoding
- **sample.md** - Markdown file with formatting

### Structured Data
- **sample.csv** - CSV file with employee data (10 rows)

### Binary Documents (to be added)
- **sample.pdf** - Regular PDF with extractable text
- **scanned.pdf** - Scanned PDF requiring OCR
- **sample.docx** - Microsoft Word document with headings and tables

## Usage

### Python Testing

```python
from document_processor import DocumentExtractor

# Test text extraction
extractor = DocumentExtractor()

# Test TXT
result = extractor.extract('tests/fixtures/sample.txt', 'txt')
print(f"Extracted {len(result['text'])} characters")

# Test MD
result = extractor.extract('tests/fixtures/sample.md', 'md')
print(f"Metadata: {result['metadata']}")

# Test CSV
result = extractor.extract('tests/fixtures/sample.csv', 'csv')
print(f"Rows: {result['metadata']['row_count']}")
```

### API Testing

```bash
# Upload sample.txt
curl -X POST http://localhost:8080/api/documents/upload \
  -H "Cookie: session=..." \
  -F "org_id=1" \
  -F "files=@tests/fixtures/sample.txt"

# Upload multiple files
curl -X POST http://localhost:8080/api/documents/upload \
  -H "Cookie: session=..." \
  -F "org_id=1" \
  -F "files=@tests/fixtures/sample.txt" \
  -F "files=@tests/fixtures/sample.md" \
  -F "files=@tests/fixtures/sample.csv"
```

## Creating Additional Test Files

### PDF Test File

You can create a test PDF using any of these methods:

1. **Using macOS Preview:**
   - Create a text file
   - Open in TextEdit
   - File → Export as PDF

2. **Using Python:**
   ```python
   from reportlab.pdfgen import canvas

   c = canvas.Canvas("sample.pdf")
   c.drawString(100, 750, "Sample PDF Document")
   c.drawString(100, 730, "This is a test PDF for extraction.")
   c.save()
   ```

3. **Using LibreOffice:**
   - Create document in Writer
   - File → Export as PDF

### DOCX Test File

Create using Microsoft Word, LibreOffice Writer, or Google Docs:
- Add headings (Heading 1, Heading 2)
- Add bulleted and numbered lists
- Add a table with 3 columns and 5 rows
- Export as .docx format

## Expected Behavior

### sample.txt
- Should extract all text content
- Metadata should include line_count and char_count
- Processing should complete in < 1 second

### sample.md
- Should extract markdown content (may strip formatting)
- Should handle code blocks
- Metadata should include line_count

### sample.csv
- Should extract and format as readable text
- Headers should be preserved
- Metadata should include row_count and column_count
- Should return structured data in result['structure']

## Validation

Run automated tests:

```bash
# Run unit tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_document_processor.py
```
