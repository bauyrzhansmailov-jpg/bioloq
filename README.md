# ExamPrep Question Bank System

Complete exam preparation system with unlimited question storage using SQLite database.

## Features
✅ **SQLite Database** - All questions stored in `question_bank.db` file
✅ **REST API** - Python backend server with HTTP API
✅ **All Question Types** - Multiple choice, True/False, Calculation, Diagram
✅ **Points System** - Assign points to individual answers
✅ **Practice Exams** - Create custom exams from filtered questions
✅ **Rich Text Editor** - Format questions with bold, italic, lists, headings
✅ **Image Support** - Upload images for questions and answers
✅ **Persistent Storage** - Questions saved to database file

## Quick Start

### 1. Start the Server

**Linux/Mac:**
```bash
./start_server.sh
```

**Windows:**
```bash
python server.py
```

**Alternative (any OS):**
```bash
python3 server.py
```

### 2. Open in Browser

Go to: http://localhost:8000

### 3. Use the Application

- **Add Questions**: Click "Add Question" tab
- **View/Edit/Delete**: Click "Question Bank" tab
- **Practice Exams**: Filter questions, click "Start Practice Exam"

## File Structure

```
exam-prep/
├── server.py              # Python backend server
├── start_server.sh        # Startup script
├── question_bank.db       # SQLite database (created automatically)
├── exam-prep.html         # Main application
├── practice-exam.html     # Practice exam page
└── README.md             # This file
```

## API Endpoints

### GET /api/questions
Get all questions from database

### POST /api/questions
Add new question
```json
{
  "text": "Question text",
  "year": "2024",
  "examSource": "IBO",
  "topics": ["Genetics", "Molecular Biology"],
  "skills": ["Верно-Неверно"],
  "answers": {...},
  "explanation": "Explanation text",
  "image": "base64..."
}
```

### PUT /api/questions/{id}
Update existing question

### DELETE /api/questions/{id}
Delete question

## Database Schema

```sql
CREATE TABLE questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    year TEXT,
    exam_source TEXT,
    topics TEXT,        -- JSON array
    skills TEXT,        -- JSON array
    answers TEXT,       -- JSON object
    explanation TEXT,
    image TEXT,         -- base64
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

## Requirements

- Python 3.6+
- Modern web browser (Chrome, Firefox, Safari, Edge)
- No additional Python packages needed (uses standard library)

## Features in Detail

### Question Types

1. **Верно-Неверно** (True/False) - Multiple selection with points
2. **Вопрос с одним верным ответом** - Single correct answer
3. **Вопрос с несколькими верными ответами** - Multiple correct answers
4. **Задание на расчет** - Calculation with text answer
5. **Задание на создание диаграммы** - Diagram upload

### Points System

For True/False questions, you can assign:
- Positive points for correct answers
- Zero or negative points for incorrect answers
- Practice exams calculate total points earned

### Practice Exam

1. Go to Question Bank tab
2. Use filters (Year, Source, Topic, Type, Search)
3. Click "🎯 Start Practice Exam"
4. Answer questions in new window
5. Submit to see score and review answers

## Backup Your Data

Your questions are stored in `question_bank.db`. To backup:
1. Stop the server
2. Copy `question_bank.db` to a safe location
3. To restore, replace the file and restart

## Troubleshooting

**Server won't start:**
- Make sure port 8000 is not in use
- Check Python 3 is installed: `python3 --version`

**Questions not loading:**
- Check server is running at http://localhost:8000
- Open browser console (F12) for error messages
- Make sure database file has write permissions

**Practice exam not opening:**
- Make sure both HTML files are in same directory as server
- Check browser allows popups from localhost

## Development

Built with:
- **Backend**: Python 3 + SQLite3 + http.server
- **Frontend**: Vanilla JavaScript + HTML5 + CSS3
- **No frameworks required** - Pure web technologies

## License

Free to use for educational purposes.
