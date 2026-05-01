================================================================================
AI SaaS Platform
================================================================================

An enterprise-grade AI SaaS platform featuring a three-panel dashboard
(Sidebar, Chat, Preview) where authenticated users interact with a multi-agent
AI system via real-time WebSocket streaming. The AI system follows a multi-phase
execution flow (Phases 0-7) powered by LangChain agents using the Anthropic
Claude API to generate structured deliverables: User Stories (Markdown),
PowerPoint slides (JSON), and UI Prototypes.

================================================================================
PREREQUISITES
================================================================================

Ensure the following are installed on your system (Windows or macOS):

  - Python 3.12 or higher
  - Node.js 20 or higher
  - npm (comes with Node.js)
  - pip (comes with Python)
  - git

================================================================================
SETUP INSTRUCTIONS
================================================================================

These instructions work on both Windows and macOS. All commands use
cross-platform compatible syntax.

--------------------------------------------------------------------------------
1. Clone the Repository
--------------------------------------------------------------------------------

  git clone <repository-url>
  cd ai-saas-platform

--------------------------------------------------------------------------------
2. Backend Setup (Python / FastAPI)
--------------------------------------------------------------------------------

  a) Create a virtual environment (recommended):

     Windows:
       python -m venv venv
       venv\Scripts\activate

     macOS:
       python3 -m venv venv
       source venv/bin/activate

  b) Install dependencies:

     pip install -r backend/requirements.txt

  c) Create environment file:

     Copy the .env.example file to .env in the project root and fill in
     your values:

     Windows:
       copy .env.example .env

     macOS:
       cp .env.example .env

     Edit .env and set:
       ANTHROPIC_API_KEY=your-anthropic-api-key
       SECRET_KEY=your-secret-key-for-jwt
       DATABASE_URL=sqlite:///./dev.db

  d) Run the backend server:

     uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

     The backend API will be available at http://localhost:8000

--------------------------------------------------------------------------------
3. Frontend Setup (Next.js / React)
--------------------------------------------------------------------------------

  a) Install dependencies:

     cd frontend
     npm install

  b) Create environment file:

     Create a file named .env.local in the frontend/ directory with:

       NEXT_PUBLIC_API_URL=http://localhost:8000
       NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/chat

  c) Run the frontend development server:

     npm run dev

     The frontend will be available at http://localhost:3000

================================================================================
RUNNING THE APPLICATION
================================================================================

To run the full platform, you need both the backend and frontend running
simultaneously in separate terminal windows.

Terminal 1 - Backend:

  (activate your virtual environment first)
  uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

Terminal 2 - Frontend:

  cd frontend
  npm run dev

Once both are running:
  1. Open http://localhost:3000 in your browser
  2. Register a new account
  3. Log in with your credentials
  4. Start a new chat session from the sidebar
  5. Interact with the AI agents via the chat panel
  6. View generated outputs in the preview panel

================================================================================
ENVIRONMENT VARIABLES REFERENCE
================================================================================

Backend (.env in project root):

  ANTHROPIC_API_KEY    (required) Your Anthropic Claude API key for AI agents
  SECRET_KEY           (required) Secret key used for JWT token signing
  DATABASE_URL         (optional) Database connection string
                       Default: sqlite:///./dev.db

Frontend (frontend/.env.local):

  NEXT_PUBLIC_API_URL  (required) Backend API base URL
                       Default: http://localhost:8000
  NEXT_PUBLIC_WS_URL   (required) Backend WebSocket URL
                       Default: ws://localhost:8000/ws/chat

================================================================================
TESTING
================================================================================

Backend Tests (pytest + Hypothesis):

  Run from the project root with your virtual environment activated:

    pytest backend/tests/ -v

  This runs both unit tests and property-based tests using Hypothesis.

Frontend Tests (Vitest + fast-check):

  Run from the frontend/ directory:

    cd frontend
    npm test

  This runs both unit tests and property-based tests using fast-check.

  Additional frontend commands:

    npm run lint       Run ESLint checks
    npm run build      Create production build

================================================================================
NPM SCRIPTS (frontend/package.json)
================================================================================

  npm run dev          Start Next.js development server
  npm run build        Create optimized production build
  npm run start        Start production server
  npm test             Run test suite (Vitest)
  npm run lint         Run ESLint

All scripts are cross-platform and work on both Windows and macOS without
modification.

================================================================================
CROSS-PLATFORM NOTES
================================================================================

  - All file paths in the codebase use forward slashes or the Node.js path
    module for cross-platform compatibility
  - No OS-specific binaries or system libraries are required
  - Python dependencies are pure Python or have pre-built wheels for both
    Windows and macOS
  - Node.js dependencies are JavaScript-only or have pre-built binaries for
    both platforms
  - The SQLite database requires no external database server installation
  - Virtual environment activation differs between Windows and macOS (see
    setup instructions above)

================================================================================
PROJECT STRUCTURE
================================================================================

  ai-saas-platform/
  |-- .env.example           Environment variable template
  |-- README.txt             This file
  |-- backend/               Python/FastAPI backend
  |   |-- app/
  |   |   |-- main.py        FastAPI entry point
  |   |   |-- api/           REST and WebSocket endpoints
  |   |   |-- agents/        LangChain agent definitions
  |   |   |-- core/          Config, security, dependencies
  |   |   |-- models/        SQLAlchemy and Pydantic models
  |   |   |-- services/      Business logic services
  |   |-- requirements.txt   Python dependencies
  |   |-- pyproject.toml     Project and pytest configuration
  |   |-- tests/             Backend test suite
  |-- frontend/              Next.js/React frontend
  |   |-- src/
  |   |   |-- app/           Next.js App Router pages
  |   |   |-- components/    React components
  |   |   |-- hooks/         Custom React hooks
  |   |   |-- lib/           Utilities and parsers
  |   |   |-- styles/        Global styles and theme
  |   |   |-- types/         TypeScript type definitions
  |   |-- package.json       Node.js dependencies and scripts
  |   |-- tsconfig.json      TypeScript configuration
