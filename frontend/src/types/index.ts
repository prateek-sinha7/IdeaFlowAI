export interface User {
  id: string;
  email: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface ChatSession {
  id: string;
  title: string;
  lastActivity: string;
  createdAt: string;
}

export interface ChatMessage {
  id: string;
  chatSessionId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  steps?: ProcessStep[];
}

export interface StreamMessage {
  type: "stream" | "complete" | "error" | "phase_start" | "phase_end" | "title_update" | "step";
  chunk?: string;
  section?: string;
  data?: FinalOutput | ErrorDetail | ProcessStep;
}

export interface ProcessStep {
  id: string;
  label: string;
  detail?: string;
  status: "running" | "done" | "error";
  icon?: string;
  timestamp?: string;
}

export interface ErrorDetail {
  message: string;
  code?: string;
}

export interface FinalOutput {
  auth: object | null;
  realtime: object | null;
  dashboard: object | null;
  discovery: object | null;
  requirements: object | null;
  user_stories: object | null;
  ppt: SlideData | null;
  prototype: PrototypeDefinition | null;
  ui_design: object | null;
  ui_preview: object | null;
}

export interface SlideData {
  slides: Slide[];
}

export interface Slide {
  title: string;
  content: BulletPoint[];
  type: "text" | "chart" | "table" | "comparison" | "icon";
  colorScheme: {
    background: string;
    text: string;
    accent: string;
  };
}

export interface BulletPoint {
  text: string;
  subPoints?: string[];
}

export interface PrototypeDefinition {
  pages: PrototypePage[];
  navigation: NavigationConfig;
  behavior: BehaviorConfig;
}

export interface PrototypePage {
  name: string;
  route: string;
  components: PrototypeComponent[];
}

export interface PrototypeComponent {
  type: string;
  props: Record<string, unknown>;
  children?: PrototypeComponent[];
}

export interface NavigationConfig {
  routes: Record<string, string>;
  defaultRoute?: string;
}

export interface BehaviorConfig {
  interactions: Record<string, string>;
  animations?: Record<string, string>;
}

export interface UserStoryDocument {
  epics: Epic[];
}

export interface Epic {
  title: string;
  description: string;
  stories: Story[];
}

export interface Story {
  title: string;
  description: string;
  acceptanceCriteria: string[];
}
