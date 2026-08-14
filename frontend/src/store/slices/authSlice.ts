import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { User } from "@/types/index";

export interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
}

const initialState: AuthState = {
  token: null,
  user: null,
  isAuthenticated: false,
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    // Dispatched once a page confirms a valid token is present (mirrors the
    // existing getToken()/localStorage check in dashboard/page.tsx and
    // workflow/page.tsx) — this is the "user is signed in" signal the
    // agents slice's listener middleware reacts to.
    signedIn(state, action: PayloadAction<{ token: string; user?: User | null }>) {
      state.token = action.payload.token;
      state.user = action.payload.user ?? state.user;
      state.isAuthenticated = true;
    },
    userLoaded(state, action: PayloadAction<User>) {
      state.user = action.payload;
    },
    signedOut(state) {
      state.token = null;
      state.user = null;
      state.isAuthenticated = false;
    },
  },
});

export const { signedIn, userLoaded, signedOut } = authSlice.actions;
export default authSlice.reducer;
