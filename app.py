# app.py - Main Flask Application
from flask import Flask, render_template, request, jsonify, session
import os
import PyPDF2
import re
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.cluster import KMeans
from transformers import pipeline
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from werkzeug.utils import secure_filename
import uuid
import logging
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

# Download required NLTK data
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
except:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Create uploads directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize models (will be loaded on first use to save startup time)
sentence_model = None
summarizer = None

def load_models():
    """Load AI models on first use"""
    global sentence_model, summarizer
    try:
        if sentence_model is None:
            print("Loading Sentence Transformer model...")
            sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        if summarizer is None:
            print("Loading Summarization model...")
            summarizer = pipeline("summarization", 
                                model="facebook/bart-large-cnn",
                                max_length=150, 
                                min_length=50, 
                                do_sample=False)
        print("Models loaded successfully!")
    except Exception as e:
        print(f"Error loading models: {e}")
        return False
    return True

class StudyBot:
    def __init__(self):
        self.books_data = {}
    
    def extract_pdf_text(self, pdf_path):
        """Extract text from PDF file"""
        try:
            text = ""
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text if text.strip() else None
        except Exception as e:
            logging.error(f"Error extracting PDF: {e}")
            return None
    
    def detect_chapters(self, text):
        """Detect chapters in the text using regex patterns"""
        # Common chapter patterns
        chapter_patterns = [
            r'Chapter\s+(\d+)[:\.\s]*([^\n]*)',
            r'CHAPTER\s+(\d+)[:\.\s]*([^\n]*)',
            r'(\d+)\.\s*([A-Z][^\n\.]*)',
            r'Unit\s+(\d+)[:\.\s]*([^\n]*)',
            r'UNIT\s+(\d+)[:\.\s]*([^\n]*)',
            r'Section\s+(\d+)[:\.\s]*([^\n]*)',
            r'SECTION\s+(\d+)[:\.\s]*([^\n]*)'
        ]
        
        chapters = {}
        text_lines = text.split('\n')
        
        for i, line in enumerate(text_lines):
            line = line.strip()
            if not line or len(line) < 5:
                continue
                
            for pattern in chapter_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    chapter_num = match.group(1)
                    chapter_title = match.group(2).strip() if len(match.groups()) > 1 else f"Chapter {chapter_num}"
                    
                    # Clean chapter title
                    if not chapter_title or len(chapter_title) < 3:
                        chapter_title = f"Chapter {chapter_num}"
                    
                    # Extract chapter content (next lines until next chapter or end)
                    content_lines = []
                    for j in range(i + 1, min(i + 200, len(text_lines))):
                        if j >= len(text_lines):
                            break
                        next_line = text_lines[j].strip()
                        
                        # Check if we hit another chapter
                        is_next_chapter = False
                        for p in chapter_patterns:
                            if re.search(p, next_line, re.IGNORECASE):
                                is_next_chapter = True
                                break
                        
                        if is_next_chapter:
                            break
                        
                        if next_line and len(next_line) > 3:
                            content_lines.append(next_line)
                    
                    content = ' '.join(content_lines)
                    if len(content) > 200:  # Only include substantial content
                        chapters[chapter_num] = {
                            'title': chapter_title,
                            'content': content[:5000],  # Limit content length
                            'line_start': i
                        }
                    break
        
        # If no chapters found, create artificial sections
        if not chapters:
            print("No chapters detected, creating artificial sections...")
            sentences = sent_tokenize(text)
            chunk_size = max(len(sentences) // 8, 50)  # Create ~8 sections
            
            if chunk_size > 0:
                section_num = 1
                for i in range(0, len(sentences), chunk_size):
                    content = ' '.join(sentences[i:i + chunk_size])
                    if len(content) > 100:
                        chapters[str(section_num)] = {
                            'title': f"Section {section_num}",
                            'content': content[:5000],
                            'line_start': i
                        }
                        section_num += 1
        
        print(f"Detected {len(chapters)} chapters/sections")
        return chapters
    
    def generate_summary(self, text):
        """Generate summary using BART"""
        try:
            if not text or len(text.strip()) < 100:
                return "Content too short to summarize."
                
            # Clean and prepare text
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Split text into manageable chunks
            max_chunk_length = 800
            chunks = []
            
            sentences = sent_tokenize(text)
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk + sentence) < max_chunk_length:
                    current_chunk += " " + sentence
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence
            
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            summaries = []
            for chunk in chunks[:3]:  # Limit to first 3 chunks
                if len(chunk) > 100:
                    try:
                        summary = summarizer(chunk)[0]['summary_text']
                        summaries.append(summary)
                    except Exception as e:
                        print(f"Summarization error for chunk: {e}")
                        continue
            
            if summaries:
                return ' '.join(summaries)
            else:
                return self.extractive_summary(text)
                
        except Exception as e:
            print(f"Error in summarization: {e}")
            return self.extractive_summary(text)
    
    def extractive_summary(self, text):
        """Fallback extractive summary using sentence ranking"""
        try:
            sentences = sent_tokenize(text)
            if len(sentences) <= 3:
                return text
            
            # Simple ranking based on sentence position and length
            scored_sentences = []
            for i, sentence in enumerate(sentences):
                if len(sentence.strip()) < 10:
                    continue
                    
                score = 0
                # Position score (beginning sentences are often important)
                if i < len(sentences) * 0.3:
                    score += 2
                
                # Length score (moderate length sentences are often good)
                words = word_tokenize(sentence.lower())
                if 10 <= len(words) <= 35:
                    score += 1
                
                # Keyword bonus
                important_words = ['important', 'key', 'main', 'primary', 'essential', 
                                 'definition', 'principle', 'concept', 'theory']
                if any(word in sentence.lower() for word in important_words):
                    score += 1
                
                scored_sentences.append((score, sentence.strip()))
            
            # Get top sentences
            scored_sentences.sort(reverse=True, key=lambda x: x[0])
            top_sentences = [sent for score, sent in scored_sentences[:4]]
            
            return ' '.join(top_sentences)
        except:
            return text[:400] + "..." if len(text) > 400 else text
    
    def extract_key_points(self, text):
        """Extract key points from text"""
        try:
            sentences = sent_tokenize(text)
            
            # Keywords that often indicate important points
            important_keywords = [
                'important', 'key', 'main', 'primary', 'essential', 'crucial',
                'definition', 'theorem', 'principle', 'law', 'rule', 'formula',
                'note', 'remember', 'conclusion', 'result', 'therefore', 'thus',
                'concept', 'theory', 'method', 'process', 'step'
            ]
            
            key_points = []
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 15:
                    continue
                    
                sentence_lower = sentence.lower()
                
                # Check for important keywords
                keyword_count = sum(1 for keyword in important_keywords if keyword in sentence_lower)
                if keyword_count > 0:
                    key_points.append(sentence)
                
                # Check for numbered/bulleted points
                if re.match(r'^\s*[\d\w]\.\s', sentence) or sentence.startswith('•'):
                    key_points.append(sentence)
                
                # Check for sentences with definitions
                if ':' in sentence and ('is ' in sentence_lower or 'are ' in sentence_lower):
                    key_points.append(sentence)
            
            # Remove duplicates and sort by relevance
            key_points = list(dict.fromkeys(key_points))
            
            # If no specific key points found, extract first few sentences
            if not key_points:
                key_points = [s for s in sentences[:5] if len(s.strip()) > 20]
            
            return key_points[:8]  # Limit to 8 points
        except Exception as e:
            print(f"Error extracting key points: {e}")
            return ["Unable to extract key points from this chapter."]
    
    def explain_in_simple_words(self, text):
        """Provide simple explanation"""
        try:
            sentences = sent_tokenize(text)
            
            # Word replacements for simplification
            replacements = {
                'utilize': 'use', 'demonstrate': 'show', 'consequently': 'so',
                'furthermore': 'also', 'therefore': 'so', 'however': 'but',
                'nevertheless': 'but', 'subsequently': 'then', 'prior to': 'before',
                'in order to': 'to', 'due to the fact that': 'because',
                'methodology': 'method', 'facilitate': 'help', 'implement': 'do',
                'obtain': 'get', 'acquire': 'get', 'commence': 'start'
            }
            
            simple_explanation = []
            for sentence in sentences[:6]:  # Take first 6 sentences
                if len(sentence.strip()) < 10:
                    continue
                
                # Apply replacements
                simplified = sentence
                for complex_word, simple_word in replacements.items():
                    simplified = re.sub(r'\b' + complex_word + r'\b', simple_word, simplified, flags=re.IGNORECASE)
                
                # Break down very long sentences
                if len(simplified.split()) > 25:
                    # Try to split at conjunctions
                    parts = re.split(r'[,;](?=\s)', simplified)
                    if len(parts) > 1:
                        simplified = parts[0] + '.'
                
                simple_explanation.append(simplified.strip())
            
            result = ' '.join(simple_explanation)
            return result if result else "This chapter discusses important concepts that are explained in detail."
            
        except Exception as e:
            print(f"Error in simple explanation: {e}")
            return "This chapter covers important topics that help understand the subject better."
    
    def process_book(self, pdf_path, book_id):
        """Process uploaded book"""
        print(f"Processing book: {pdf_path}")
        text = self.extract_pdf_text(pdf_path)
        if not text:
            print("Failed to extract text from PDF")
            return False
        
        print(f"Extracted text length: {len(text)} characters")
        chapters = self.detect_chapters(text)
        
        if not chapters:
            print("No chapters detected")
            return False
        
        self.books_data[book_id] = {
            'full_text': text,
            'chapters': chapters,
            'processed': True
        }
        
        print(f"Book processed successfully with {len(chapters)} chapters")
        return True
    
    def get_chapter_analysis(self, book_id, chapter_number):
        """Get comprehensive analysis of a chapter"""
        if book_id not in self.books_data:
            return {"error": "Book not found. Please upload a book first."}
        
        chapters = self.books_data[book_id]['chapters']
        
        if str(chapter_number) not in chapters:
            available_chapters = list(chapters.keys())
            return {
                "error": f"Chapter {chapter_number} not found. Available chapters: {', '.join(available_chapters)}"
            }
        
        chapter_data = chapters[str(chapter_number)]
        content = chapter_data['content']
        
        # Load models if not already loaded
        models_loaded = load_models()
        if not models_loaded:
            return {"error": "Failed to load AI models. Please try again."}
        
        try:
            print(f"Analyzing chapter {chapter_number}...")
            
            analysis = {
                'chapter_title': chapter_data['title'],
                'chapter_number': chapter_number,
                'summary': self.generate_summary(content),
                'key_points': self.extract_key_points(content),
                'simple_explanation': self.explain_in_simple_words(content),
                'word_count': len(content.split())
            }
            
            print(f"Analysis completed for chapter {chapter_number}")
            return analysis
            
        except Exception as e:
            logging.error(f"Error in chapter analysis: {e}")
            return {"error": f"Error processing chapter analysis: {str(e)}"}

# Initialize the bot
study_bot = StudyBot()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_book():
    try:
        if 'book' not in request.files:
            return jsonify({'error': 'No file uploaded'})
        
        file = request.files['book']
        if file.filename == '':
            return jsonify({'error': 'No file selected'})
        
        if file and file.filename.lower().endswith('.pdf'):
            # Generate unique book ID
            book_id = str(uuid.uuid4())
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{book_id}_{filename}")
            
            file.save(file_path)
            print(f"File saved: {file_path}")
            
            # Process the book
            success = study_bot.process_book(file_path, book_id)
            
            if success:
                session['current_book_id'] = book_id
                available_chapters = list(study_bot.books_data[book_id]['chapters'].keys())
                
                return jsonify({
                    'success': True,
                    'book_id': book_id,
                    'available_chapters': available_chapters,
                    'message': f'Book uploaded successfully! Found {len(available_chapters)} chapters/sections.'
                })
            else:
                return jsonify({'error': 'Failed to process PDF file. Please ensure it contains readable text.'})
        else:
            return jsonify({'error': 'Please upload a PDF file'})
    
    except Exception as e:
        logging.error(f"Upload error: {e}")
        return jsonify({'error': f'An error occurred during upload: {str(e)}'})

@app.route('/analyze', methods=['POST'])
def analyze_chapter():
    try:
        data = request.get_json()
        chapter_number = data.get('chapter_number')
        book_id = session.get('current_book_id')
        
        if not book_id:
            return jsonify({'error': 'No book uploaded. Please upload a book first.'})
        
        if not chapter_number:
            return jsonify({'error': 'Please provide a chapter number'})
        
        print(f"Analyzing chapter {chapter_number} for book {book_id}")
        analysis = study_bot.get_chapter_analysis(book_id, chapter_number)
        return jsonify(analysis)
    
    except Exception as e:
        logging.error(f"Analysis error: {e}")
        return jsonify({'error': f'An error occurred during analysis: {str(e)}'})

@app.route('/chapters')
def get_chapters():
    book_id = session.get('current_book_id')
    if not book_id or book_id not in study_bot.books_data:
        return jsonify({'error': 'No book uploaded'})
    
    chapters = study_bot.books_data[book_id]['chapters']
    chapter_list = [
        {'number': num, 'title': data['title']} 
        for num, data in chapters.items()
    ]
    
    return jsonify({'chapters': chapter_list})

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('uploads', exist_ok=True)
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)