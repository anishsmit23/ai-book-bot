/* ============================================================
   Study Bot – Frontend Logic
   ============================================================ */

class StudyBot {
    constructor() {
        this.currentBookId    = null;
        this.availableChapters = [];
        this.currentAnalysis  = null;
        this.initializeEventListeners();
    }

    /* ---- Event wiring ---- */
    initializeEventListeners() {
        // Upload area click → trigger hidden file input
        document.getElementById('upload-area').addEventListener('click', () => {
            document.getElementById('book-upload').click();
        });

        // File selected via input
        document.getElementById('book-upload').addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadBook(e.target.files[0]);
            }
        });

        // Analyze button
        document.getElementById('analyze-btn').addEventListener('click', () => {
            const chapterNumber = document.getElementById('chapter-input').value;
            if (chapterNumber) {
                this.analyzeChapter(chapterNumber);
            } else {
                this.showError('Please enter a chapter number');
            }
        });

        // Enter key in chapter number input
        document.getElementById('chapter-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('analyze-btn').click();
            }
        });

        // "Analyze Another Chapter" button
        document.getElementById('analyze-another').addEventListener('click', () => {
            this.showChapterSelection();
        });

        // "Download Notes" button
        document.getElementById('download-notes').addEventListener('click', () => {
            this.downloadNotes();
        });

        // "Retry" button in error state
        document.getElementById('retry-analysis').addEventListener('click', () => {
            const chapterNumber = document.getElementById('chapter-input').value;
            if (chapterNumber) {
                this.analyzeChapter(chapterNumber);
            }
        });

        /* ---- Drag-and-drop support ---- */
        const uploadArea = document.getElementById('upload-area');

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, this.preventDefaults, false);
            document.body.addEventListener(eventName, this.preventDefaults, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => {
                uploadArea.classList.add('drag-over', 'border-opacity-100', 'bg-white', 'bg-opacity-10');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => {
                uploadArea.classList.remove('drag-over', 'border-opacity-100', 'bg-white', 'bg-opacity-10');
            }, false);
        });

        uploadArea.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.uploadBook(files[0]);
            }
        }, false);
    }

    /* ---- Helpers ---- */
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    showElement(id) {
        const el = document.getElementById(id);
        if (el) { el.classList.remove('hidden'); }
    }

    hideElement(id) {
        const el = document.getElementById(id);
        if (el) { el.classList.add('hidden'); }
    }

    showError(message) {
        document.getElementById('error-message').textContent = message;
        this.showElement('upload-error');
        setTimeout(() => this.hideElement('upload-error'), 5000);
    }

    showTemporaryMessage(message, type = 'info') {
        const messageDiv = document.createElement('div');
        const colorClass = type === 'success' ? 'bg-green-500'
                         : type === 'error'   ? 'bg-red-500'
                         :                      'bg-blue-500';
        const iconClass  = type === 'success' ? 'fa-check-circle'
                         : type === 'error'   ? 'fa-exclamation-triangle'
                         :                      'fa-info-circle';

        messageDiv.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 ${colorClass} text-white`;
        messageDiv.innerHTML = `
            <div class="flex items-center">
                <i class="fas ${iconClass} mr-2"></i>
                <span>${message}</span>
            </div>`;

        document.body.appendChild(messageDiv);
        setTimeout(() => messageDiv.remove(), 3000);
    }

    /* ---- Upload ---- */
    async uploadBook(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            this.showError('Please upload a PDF file');
            return;
        }
        if (file.size > 50 * 1024 * 1024) {
            this.showError('File size must be less than 50 MB');
            return;
        }

        const formData = new FormData();
        formData.append('book', file);

        // Show loading, hide previous status messages
        this.showElement('upload-status');
        this.hideElement('upload-success');
        this.hideElement('upload-error');

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            this.hideElement('upload-status');

            if (result.success) {
                this.currentBookId     = result.book_id;
                this.availableChapters = result.available_chapters;

                document.getElementById('success-message').textContent = result.message;
                this.showElement('upload-success');

                // Auto-advance to chapter selection after 3 seconds
                setTimeout(() => this.showChapterSelection(), 3000);
            } else {
                this.showError(result.error || 'Upload failed');
            }
        } catch (error) {
            this.hideElement('upload-status');
            this.showError('Upload failed. Please check your internet connection and try again.');
            console.error('Upload error:', error);
        }
    }

    /* ---- Chapter selection ---- */
    showChapterSelection() {
        this.showElement('chapter-section');
        this.hideElement('analysis-section');
        document.getElementById('chapter-input').value = '';
        document.getElementById('chapter-section').scrollIntoView({ behavior: 'smooth' });
        this.createChapterButtons();
    }

    createChapterButtons() {
        const container = document.getElementById('chapter-buttons');
        container.innerHTML = '';

        // Sort chapters numerically
        const sorted = [...this.availableChapters].sort((a, b) => parseInt(a) - parseInt(b));

        // Render up to the first 24 as quick-click buttons
        sorted.slice(0, 24).forEach(num => {
            const btn = document.createElement('button');
            btn.className = 'px-3 py-2 bg-white bg-opacity-20 text-white rounded-lg hover:bg-opacity-30 transition-all duration-200 text-sm font-medium border border-white border-opacity-20 hover:border-opacity-40';
            btn.textContent = num;
            btn.addEventListener('click', () => {
                document.getElementById('chapter-input').value = num;
                this.analyzeChapter(num);
            });
            container.appendChild(btn);
        });

        // Show overflow notice when there are more than 24 chapters
        if (sorted.length > 24) {
            const info = document.createElement('div');
            info.className = 'col-span-full text-center text-white opacity-75 text-sm mt-2';
            info.textContent = `Showing first 24 chapters. Total: ${sorted.length} chapters available.`;
            container.appendChild(info);
        }
    }

    /* ---- Analysis ---- */
    async analyzeChapter(chapterNumber) {
        this.showElement('analysis-section');
        this.showElement('analysis-loading');
        this.hideElement('analysis-results');
        this.hideElement('analysis-error');

        document.getElementById('analysis-section').scrollIntoView({ behavior: 'smooth' });

        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chapter_number: chapterNumber })
            });
            const result = await response.json();
            this.hideElement('analysis-loading');

            if (result.error) {
                document.getElementById('analysis-error-message').textContent = result.error;
                this.showElement('analysis-error');
            } else {
                this.displayAnalysis(result);
                this.showElement('analysis-results');
            }
        } catch (error) {
            this.hideElement('analysis-loading');
            document.getElementById('analysis-error-message').textContent =
                'Failed to analyze chapter. Please check your internet connection and try again.';
            this.showElement('analysis-error');
            console.error('Analysis error:', error);
        }
    }

    displayAnalysis(analysis) {
        this.currentAnalysis = analysis;

        // Title + metadata
        document.getElementById('chapter-title').textContent =
            analysis.chapter_title || `Chapter ${analysis.chapter_number}`;
        document.getElementById('chapter-info').textContent =
            `Chapter ${analysis.chapter_number} • ${analysis.word_count} words`;

        // Summary
        document.getElementById('summary-content').textContent =
            analysis.summary || 'No summary available.';

        // Key points
        const list = document.getElementById('key-points-list');
        list.innerHTML = '';
        if (analysis.key_points && analysis.key_points.length > 0) {
            analysis.key_points.forEach(point => {
                const li = document.createElement('li');
                li.className = 'flex items-start space-x-3';
                li.innerHTML = `
                    <i class="fas fa-chevron-right text-green-400 text-sm mt-1 flex-shrink-0"></i>
                    <span class="text-sm leading-relaxed">${point}</span>`;
                list.appendChild(li);
            });
        } else {
            list.innerHTML = '<li class="text-white opacity-75">No key points extracted.</li>';
        }

        // Simple explanation
        document.getElementById('simple-explanation').textContent =
            analysis.simple_explanation || 'No simple explanation available.';
    }

    /* ---- Download notes ---- */
    downloadNotes() {
        if (!this.currentAnalysis) {
            this.showError('No analysis data available for download');
            return;
        }

        const a = this.currentAnalysis;
        const notes = [
            'STUDY NOTES',
            '===========',
            '',
            `Chapter: ${a.chapter_title}`,
            `Chapter Number: ${a.chapter_number}`,
            `Word Count: ${a.word_count}`,
            `Generated: ${new Date().toLocaleString()}`,
            '',
            'CHAPTER SUMMARY',
            '===============',
            a.summary,
            '',
            'KEY POINTS',
            '==========',
            a.key_points
                ? a.key_points.map((pt, i) => `${i + 1}. ${pt}`).join('\n')
                : 'No key points available',
            '',
            'SIMPLE EXPLANATION',
            '==================',
            a.simple_explanation,
            '',
            '---',
            'Generated by Study Bot AI'
        ].join('\n');

        try {
            const blob = new Blob([notes], { type: 'text/plain;charset=utf-8' });
            const url  = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href  = url;
            link.download = `Chapter_${a.chapter_number}_${a.chapter_title.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50)}_Notes.txt`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);

            this.showTemporaryMessage('Notes downloaded successfully!', 'success');
        } catch (error) {
            console.error('Download error:', error);
            this.showError('Failed to download notes. Please try again.');
        }
    }
}

/* ---- Boot ---- */
document.addEventListener('DOMContentLoaded', () => {
    new StudyBot();

    // Smooth page fade-in
    document.body.style.opacity  = '0';
    document.body.style.transition = 'opacity 0.5s ease-in';
    setTimeout(() => { document.body.style.opacity = '1'; }, 100);
});

/* ---- Subtle cursor sparkle effect ---- */
document.addEventListener('mousemove', (e) => {
    const cursor = document.createElement('div');
    cursor.style.cssText = [
        'position: fixed',
        'width: 20px',
        'height: 20px',
        'border-radius: 50%',
        'background: radial-gradient(circle, rgba(255,255,255,0.3) 0%, transparent 70%)',
        'pointer-events: none',
        `left: ${e.clientX - 10}px`,
        `top: ${e.clientY - 10}px`,
        'z-index: 9999',
        'animation: fade-out 1s ease-out forwards'
    ].join(';');

    document.body.appendChild(cursor);
    setTimeout(() => { if (cursor.parentNode) { cursor.parentNode.removeChild(cursor); } }, 1000);
});
