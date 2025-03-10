# ai/ai_utils.py

import pdfplumber
from openai import OpenAI

client = OpenAI(api_key='YOUR_API_KEY')

def extract_text(pdf_path, max_pages=5):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:5]:  # Limit to first 5 pages
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def detect_bates_with_ai(pdf_text):
    prompt = f"""
    Determine if the following text extracted from a PDF contains Bates labeling.

    Text:
    '''{pdf_text[:4000]}'''

    Instructions:
    - Answer clearly with "Yes" or "No".
    - If "Yes", specify the exact Bates numbering pattern detected.
    """
    
    client = OpenAI(api_key='YOUR_API_KEY')

    response = client.chat.completions.create(
        model='gpt-4-turbo',
        messages=[{'role': 'user', 'content': prompt}],
        temperature=0,
    )

    content = response.choices[0].message.content.strip()
    return content
