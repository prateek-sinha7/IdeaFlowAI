# Implementation Plan: AI SaaS Platform

## Overview

This plan implements an enterprise-grade AI SaaS platform with a Python/FastAPI backend and React/Next.js frontend. The implementation proceeds incrementally: project scaffolding → backend auth & data layer → backend AI agents & WebSocket streaming → frontend auth & dashboard → frontend real-time chat & preview → integration wiring. Each task builds on the previous, ensuring no orphaned code.

## Tasks

- [x] 1. Set up project structure, dependencies, and configuration
  - [x] 1.1 Create backend project scaffolding
    - Create `backend/` directory with `app/main.py` (FastAPI entry point), `app/core/config.py` (settings with `ANTHROPIC_API_KEY`, `SECRET_KEY`, `DATABASE_URL`), `app/core/security.py` (placeholder), `app/models/`, `app/api/`, `app/agents/`, `app/services/`
    - Create `backend/requirements.txt` with fastapi, uvicorn, sqlalchemy, pydantic[email], python-jose[cryptography], passlib[bcrypt], langchain, langchain-anthropic, websockets, python-dotenv, pytest, hypothesis
    - Create `backend/pyproject.toml` with pytest configuration
    - Create `.env.example` with `ANTHROPIC_API_KEY`, `SECRET_KEY`, `DATABASE_URL=sqlite:///./dev.db`
    - _Requirements: 14.5, 14.6, 20.1, 20.2_

  - [x] 1.2 Create frontend project scaffolding
    - Initialize Next.js app in `frontend/` with TypeScript, App Router, Tailwind CSS
    - Create directory structure: `src/app/login/`, `src/app/register/`, `src/app/dashboard/`, `src/components/layout/`, `src/components/chat/`, `src/components/preview/`, `src/components/sidebar/`, `src/components/ui/`, `src/hooks/`, `src/lib/`, `src/styles/`, `src/types/`
    - Add dependencies: fast-check (dev), vitest (dev), @testing-library/react (dev), @testing-library/jest-dom (dev), jsdom (dev)
    - _Requirements: 20.1, 20.3_

  - [x] 1.3 Create shared TypeScript type definitions
    - Create `frontend/src/types/index.ts` with all interfaces from the design: `User`, `AuthResponse`, `ChatSession`, `ChatMessage`, `StreamMessage`, `FinalOutput`, `SlideData`, `Slide`, `BulletPoint`, `PrototypeDefinition`, `PrototypePage`, `PrototypeComponent`, `UserStoryDocument`, `Epic`, `Story`
    - _Requirements: 15.2, 19.1_

  - [x] 1.4 Create the enterprise-dark design system tokens and global styles
    - Create `frontend/src/styles/theme.ts` with color tokens: Navy Blue (#001f3f), White (#FFFFFF), Grey (#AAAAAA), Black (#000000)
    - Create `frontend/src/styles/globals.css` with Tailwind config, base dark theme styles, typing animation keyframes, fade-in transition classes, hover effect utilities
    - Update `tailwind.config.ts` to extend theme with enterprise-dark palette colors
    - _Requirements: 11.1, 11.2, 11.4, 11.5, 11.6, 11.7_

- [x] 2. Implement backend database models and auth API
  - [x] 2.1 Create SQLAlchemy models and database setup
    - Create `backend/app/models/database.py` with SQLite engine, SessionLocal, Base
    - Create `backend/app/models/user.py` with `User` model (id UUID, email unique indexed, password_hash, created_at, updated_at)
    - Create `backend/app/models/chat.py` with `ChatSession` model (id UUID, user_id FK, title, last_activity, created_at, final_output nullable JSON string) and `Message` model (id UUID, chat_session_id FK, role, content, created_at)
    - Create Pydantic request/response schemas in `backend/app/models/schemas.py`: `RegisterRequest`, `LoginRequest`, `UserResponse`, `AuthResponse`, `ChatSessionResponse`, `MessageResponse`, `StreamMessageModel`, `FinalOutputModel`
    - Wire database initialization in `app/main.py` startup event
    - _Requirements: 1.1, 1.5, 16.1_

  - [x] 2.2 Implement JWT and password security utilities
    - Implement `backend/app/core/security.py` with: `hash_password(password) -> str` using bcrypt, `verify_password(plain, hashed) -> bool`, `create_access_token(user_id) -> str` with 24h expiry, `decode_access_token(token) -> dict` with signature validation
    - Implement `backend/app/core/dependencies.py` with `get_current_user` dependency that extracts and validates JWT from Authorization header, returns 401 for expired/malformed/missing tokens
    - _Requirements: 1.5, 2.1, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 2.3 Implement auth API endpoints
    - Create `backend/app/api/auth.py` with FastAPI router
    - `POST /api/auth/register`: validate email format and password ≥8 chars, check duplicate email (409), hash password, create user, return JWT + user
    - `POST /api/auth/login`: validate credentials against bcrypt hash, return JWT with 24h expiry, return generic 401 on failure
    - `GET /api/auth/me`: return current user info from JWT
    - Register router in `app/main.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3_

  - [ ]* 2.4 Write property tests for registration and login (backend)
    - **Property 1: Registration produces a valid JWT with correct structure**
    - **Property 2: Duplicate email registration is rejected**
    - **Property 3: Invalid email format is rejected**
    - **Property 4: Short passwords are rejected**
    - **Property 5: Password hashing round-trip**
    - **Property 6: Login returns JWT with 24-hour expiry**
    - **Property 7: Invalid credentials produce generic error**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3**
    - Create `backend/tests/properties/test_auth_properties.py` using Hypothesis
    - Each test must include tag comment: `Feature: ai-saas-platform, Property N: <text>`

  - [ ]* 2.5 Write property tests for JWT validation (backend)
    - **Property 8: Valid JWT tokens are accepted**
    - **Property 9: Tampered JWT tokens are rejected**
    - **Validates: Requirements 3.1, 3.3, 3.5**
    - Create `backend/tests/properties/test_jwt_properties.py` using Hypothesis

- [x] 3. Implement backend chat API and session persistence
  - [x] 3.1 Implement chat CRUD API endpoints
    - Create `backend/app/api/chats.py` with FastAPI router
    - `POST /api/chats`: create new chat session for authenticated user, auto-generate title if not provided
    - `GET /api/chats`: list all chat sessions for user, ordered by `last_activity` descending
    - `GET /api/chats/{id}`: return full chat session with message history and optional `final_output`
    - `PUT /api/chats/{id}/messages`: append message to chat session, update `last_activity`
    - Register router in `app/main.py`
    - _Requirements: 5.1, 5.2, 5.3, 16.1, 16.2, 16.3_

  - [ ]* 3.2 Write property tests for chat session persistence (backend)
    - **Property 22: Chat session persistence round-trip**
    - **Property 23: Message updates last activity timestamp**
    - **Validates: Requirements 16.2, 16.3**
    - Create `backend/tests/properties/test_chat_properties.py` using Hypothesis

- [x] 4. Checkpoint - Backend API verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement backend LangChain agent system
  - [x] 5.1 Implement base agent class and Anthropic Claude configuration
    - Create `backend/app/agents/base.py` with `BaseAgent` class: configures ChatAnthropic LLM from `ANTHROPIC_API_KEY` env var, raises configuration error if key missing, provides `astream()` method with LangChain streaming callback, accepts system prompt in constructor
    - No fallback to other LLM providers
    - _Requirements: 14.5, 14.6, 14.7_

  - [x] 5.2 Implement specialized agents for each phase
    - Create `backend/app/agents/discovery.py` — Discovery Agent (Phase 0): asks questions to determine Output_Selection
    - Create `backend/app/agents/requirements.py` — Requirements Agent (Phase 1): generates requirements document
    - Create `backend/app/agents/user_stories.py` — User Story Agent (Phase 3): generates Markdown user stories with Epics/Stories/Acceptance Criteria
    - Create `backend/app/agents/ppt.py` — PPT Agent (Phase 4): generates slide JSON data (max 10 slides, max 5 bullets, approved palette only)
    - Create `backend/app/agents/prototype.py` — Prototype Agent (Phase 5): generates UI prototype definition with Pages/Components/Navigation/Behavior
    - Create `backend/app/agents/ui_design.py` — UI Design Agent (Phase 6): generates design specifications
    - Create `backend/app/agents/preview.py` — Preview Agent (Phase 7): compiles Final_Output
    - Each agent extends `BaseAgent` with a specialized system prompt
    - _Requirements: 8.1, 8.2, 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 10.2, 14.1, 14.2_

  - [x] 5.3 Implement Agent Orchestrator with multi-phase execution
    - Create `backend/app/agents/orchestrator.py` with `AgentOrchestrator` class
    - Implement phase pipeline: Phase 0 (Discovery) → Phase 1 (Requirements) → Phase 2 (Conditional Routing based on Output_Selection) → Phases 3–7 (sequential, skip unselected)
    - Pass accumulated context from completed phases to subsequent agents
    - On agent error: log error, mark phase as failed, continue to next phase
    - On completion: compile all phase outputs into `Final_Output` JSON with all 10 required sections; skipped phases get `null` value with `"status": "skipped"`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.3, 14.4, 15.1, 15.2, 15.4_

  - [ ]* 5.4 Write property tests for agent orchestrator (backend)
    - **Property 19: Phase execution respects Output_Selection**
    - **Property 20: Agent error resilience**
    - **Property 21: Phase context accumulation**
    - **Validates: Requirements 13.4, 13.5, 14.3, 14.4**
    - Create `backend/tests/properties/test_orchestrator_properties.py` using Hypothesis

  - [ ]* 5.5 Write property tests for Final Output (backend)
    - **Property 17: Final Output round-trip**
    - **Property 18: Final Output structural completeness**
    - **Validates: Requirements 15.2, 15.3, 15.4**
    - Create `backend/tests/properties/test_final_output_properties.py` using Hypothesis

- [x] 6. Implement backend WebSocket server
  - [x] 6.1 Implement WebSocket endpoint with JWT auth and streaming
    - Create `backend/app/api/websocket.py` with WebSocket endpoint at `/ws/chat`
    - Authenticate via JWT query parameter (`?token=<jwt>`)
    - On message received: parse `user_message` JSON, route to Agent Orchestrator
    - Stream agent response chunks as `Stream_Message` JSON objects with `type`, `chunk`, `section` fields
    - Send `phase_start` and `phase_end` messages at phase boundaries
    - On completion: send `complete` message with full `Final_Output`
    - On JWT expired during session: close connection with code 4001
    - Handle connection lifecycle (open, message, close, error)
    - Register WebSocket route in `app/main.py`; add CORS middleware for frontend origin
    - _Requirements: 6.1, 7.1, 7.2, 7.5, 8.3, 9.6, 10.3_

- [x] 7. Checkpoint - Backend complete verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement frontend authentication pages
  - [x] 8.1 Create auth API client utility
    - Create `frontend/src/lib/api.ts` with functions: `register(email, password)`, `login(email, password)`, `getMe(token)`, `createChat(token)`, `getChats(token)`, `getChat(token, id)`, `addMessage(token, chatId, content, role)`
    - Store JWT in `localStorage`, include in Authorization header for all authenticated requests
    - Base URL configurable via environment variable
    - _Requirements: 1.1, 2.1, 3.1_

  - [x] 8.2 Implement Login page
    - Create `frontend/src/app/login/page.tsx` with email/password form
    - Submit to `POST /api/auth/login` via API client
    - Display server-side validation errors inline (generic 401 message)
    - On success: store JWT in localStorage, redirect to `/dashboard`
    - Link to registration page
    - Apply enterprise-dark theme styling
    - _Requirements: 2.1, 2.2, 11.1, 11.2_

  - [x] 8.3 Implement Register page
    - Create `frontend/src/app/register/page.tsx` with email/password form
    - Client-side validation: password min 8 characters
    - Submit to `POST /api/auth/register` via API client
    - Display server-side validation errors inline (409 duplicate email, 422 validation errors with field-level details)
    - On success: store JWT in localStorage, redirect to `/dashboard`
    - Link to login page
    - Apply enterprise-dark theme styling
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 11.1, 11.2_

- [x] 9. Implement frontend dashboard layout and sidebar
  - [x] 9.1 Implement Dashboard layout with three-panel structure
    - Create `frontend/src/app/dashboard/page.tsx` as the main dashboard page
    - Create `frontend/src/components/layout/DashboardLayout.tsx` with three-panel flex layout: Sidebar (fixed 280px), ChatPanel (flex-grow), PreviewPanel (fixed 420px)
    - On screens <1024px: collapse Sidebar to toggleable overlay
    - Redirect to `/login` if no valid JWT present
    - Establish WebSocket connection on mount, tear down on unmount
    - Wrap each panel in a React Error Boundary with "Something went wrong" + retry button
    - _Requirements: 4.1, 4.2, 4.3, 7.1_

  - [x] 9.2 Implement Sidebar with chat session management
    - Create `frontend/src/components/sidebar/Sidebar.tsx` with "New Chat" button and scrollable chat session list
    - Create `frontend/src/components/sidebar/ChatSessionItem.tsx` displaying title/timestamp, highlighting active session
    - "New Chat" button: calls `POST /api/chats`, prepends new session to list without page reload
    - Chat list: ordered by `last_activity` descending, loads full message history on click
    - Apply enterprise-dark theme with hover effects on chat items
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 11.6_

- [x] 10. Implement frontend WebSocket client and chat panel
  - [x] 10.1 Implement useWebSocket custom hook
    - Create `frontend/src/hooks/useWebSocket.ts`
    - Connect to `ws://<backend>/ws/chat?token=<jwt>`
    - Parse incoming `Stream_Message` JSON, dispatch to chat and preview state
    - Implement reconnection with exponential backoff (base 1s, max 5 retries)
    - On all retries failed: expose error state for UI notification with manual reconnect
    - On server close with code 4001 (JWT expired): redirect to login
    - Expose `send(message)`, `connectionStatus`, `reconnect()`
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 10.2 Implement Chat Panel with streaming display
    - Create `frontend/src/components/chat/ChatPanel.tsx` with scrollable message list and input bar
    - Create `frontend/src/components/chat/MessageBubble.tsx` with user messages (right-aligned, dark bg) and AI messages (left-aligned, lighter bg)
    - Create `frontend/src/components/chat/TypingIndicator.tsx` with animated dots during streaming
    - Create `frontend/src/components/chat/ChatInput.tsx` with text input, send button, Enter-to-send
    - Implement auto-scroll to bottom during streaming
    - Add "Regenerate" and "Edit" actions on completed AI messages
    - Apply enterprise-dark theme with typing animation and fade-in transitions
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 11.3, 11.4, 11.5_

- [x] 11. Implement frontend preview panel with parsers
  - [x] 11.1 Implement output parsers for User Stories, PPT, and Stream Messages
    - Create `frontend/src/lib/parsers/userStoryParser.ts`: parse Markdown → `UserStoryDocument` (Epics/Stories/Acceptance Criteria), format `UserStoryDocument` → Markdown
    - Create `frontend/src/lib/parsers/pptParser.ts`: parse JSON → `SlideData`, serialize `SlideData` → JSON, return descriptive error on malformed JSON
    - Create `frontend/src/lib/parsers/streamParser.ts`: parse JSON → `StreamMessage`, serialize `StreamMessage` → JSON, log and discard malformed messages
    - _Requirements: 17.1, 17.2, 18.1, 18.2, 18.4, 19.1, 19.2, 19.4_

  - [ ]* 11.2 Write property tests for frontend parsers
    - **Property 11: User Story Markdown round-trip**
    - **Property 12: PPT slide data validation**
    - **Property 13: PPT slide JSON round-trip**
    - **Property 14: PPT malformed JSON produces descriptive error**
    - **Property 15: Stream message round-trip**
    - **Property 16: Malformed stream messages are handled gracefully**
    - **Validates: Requirements 8.4, 9.2, 9.3, 9.4, 17.1, 17.2, 17.3, 18.1, 18.2, 18.3, 18.4, 19.1, 19.2, 19.3, 19.4**
    - Create `frontend/src/__tests__/properties/` test files using fast-check

  - [x] 11.3 Implement Preview Panel with tabbed rendering
    - Create `frontend/src/components/preview/PreviewPanel.tsx` with three tabs: User Stories, PPT, Prototype
    - Create `frontend/src/components/preview/UserStoryPreview.tsx`: renders parsed Markdown as formatted HTML with Epics/Stories/Acceptance Criteria hierarchy
    - Create `frontend/src/components/preview/PPTPreview.tsx`: renders slides in carousel with prev/next navigation, each slide as a card with approved color palette
    - Create `frontend/src/components/preview/PrototypePreview.tsx`: renders prototype definition showing Pages, Components, Navigation, Behavior
    - Tab switching preserves rendered state of inactive tabs (no re-render on switch)
    - Real-time update of active tab during streaming
    - Apply enterprise-dark theme with smooth tab transitions and hover effects
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 11.6, 11.7_

  - [ ]* 11.4 Write property tests for chat session ordering and tab preservation (frontend)
    - **Property 10: Chat sessions are ordered by last activity**
    - **Property 24: Preview tab state preservation**
    - **Validates: Requirements 5.2, 12.5**
    - Create test files in `frontend/src/__tests__/properties/` using fast-check

- [x] 12. Checkpoint - Frontend complete verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Integration wiring and cross-platform finalization
  - [x] 13.1 Wire frontend to backend and verify end-to-end flow
    - Configure frontend API base URL to point to backend (e.g., `http://localhost:8000`)
    - Ensure CORS is configured on backend for frontend origin
    - Verify: register → login → create chat → send message → receive streaming response → preview renders
    - Fix any integration issues discovered during wiring
    - _Requirements: 6.1, 7.1, 7.5, 8.3, 9.6, 10.3_

  - [x] 13.2 Create cross-platform scripts and README
    - Create `README.md` with setup instructions for both Windows and macOS
    - Add cross-platform npm scripts in `frontend/package.json` (dev, build, test, lint)
    - Add cross-platform pip/python scripts or Makefile targets in `backend/` (dev, test)
    - Ensure all file paths use forward slashes or `path` module equivalents
    - Ensure no OS-specific binaries or system libraries are required
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

- [x] 14. Final checkpoint - Full platform verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at backend-complete, frontend-complete, and full-platform stages
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend uses Python 3.12.2 with FastAPI; the frontend uses Node v20.9.0 with Next.js and TypeScript
- SQLite is used for the development database; no external database server required
- The Anthropic Claude API is the sole LLM provider — no fallback to other providers
