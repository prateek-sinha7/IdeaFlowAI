import { describe, it, expect } from "vitest";
import authReducer, { signedIn, userLoaded, signedOut, type AuthState } from "./authSlice";

describe("authSlice reducer", () => {
  it("should return initial state", () => {
    const state = authReducer(undefined, { type: "@@INIT" });
    expect(state).toEqual({
      token: null,
      user: null,
      isAuthenticated: false,
    });
  });

  describe("signedIn action", () => {
    it("should set token and isAuthenticated true", () => {
      const initialState: AuthState = {
        token: null,
        user: null,
        isAuthenticated: false,
      };
      const newState = authReducer(
        initialState,
        signedIn({ token: "test-token" })
      );
      expect(newState.token).toBe("test-token");
      expect(newState.isAuthenticated).toBe(true);
    });

    it("should set token and user when provided", () => {
      const initialState: AuthState = {
        token: null,
        user: null,
        isAuthenticated: false,
      };
      const user = {
        id: "user-1",
        email: "test@example.com",
        tier: "pro" as const,
      };
      const newState = authReducer(
        initialState,
        signedIn({ token: "test-token", user })
      );
      expect(newState.token).toBe("test-token");
      expect(newState.user).toEqual(user);
      expect(newState.isAuthenticated).toBe(true);
    });

    it("should preserve existing user if not provided in payload", () => {
      const existingUser = {
        id: "user-1",
        email: "test@example.com",
        tier: "pro" as const,
      };
      const initialState: AuthState = {
        token: null,
        user: existingUser,
        isAuthenticated: false,
      };
      const newState = authReducer(
        initialState,
        signedIn({ token: "test-token" })
      );
      expect(newState.user).toEqual(existingUser);
    });

    it("should update user when explicitly provided", () => {
      const existingUser = {
        id: "old-user",
        email: "old@example.com",
        tier: "basic" as const,
      };
      const initialState: AuthState = {
        token: null,
        user: existingUser,
        isAuthenticated: false,
      };
      const newUser = {
        id: "new-user",
        email: "new@example.com",
        tier: "pro" as const,
      };
      const newState = authReducer(
        initialState,
        signedIn({ token: "test-token", user: newUser })
      );
      expect(newState.user).toEqual(newUser);
      expect(newState.user?.id).toBe("new-user");
    });

    it("should update token on subsequent signedIn calls", () => {
      let state: AuthState = authReducer(undefined, { type: "@@INIT" });
      state = authReducer(state, signedIn({ token: "token-1" }));
      expect(state.token).toBe("token-1");

      state = authReducer(state, signedIn({ token: "token-2" }));
      expect(state.token).toBe("token-2");
      expect(state.isAuthenticated).toBe(true);
    });
  });

  describe("userLoaded action", () => {
    it("should update user in state", () => {
      const initialState: AuthState = {
        token: "test-token",
        user: null,
        isAuthenticated: true,
      };
      const user = {
        id: "user-1",
        email: "test@example.com",
        tier: "pro" as const,
      };
      const newState = authReducer(initialState, userLoaded(user));
      expect(newState.user).toEqual(user);
    });

    it("should preserve token and isAuthenticated", () => {
      const initialState: AuthState = {
        token: "test-token",
        user: null,
        isAuthenticated: true,
      };
      const user = {
        id: "user-1",
        email: "test@example.com",
        tier: "enterprise" as const,
      };
      const newState = authReducer(initialState, userLoaded(user));
      expect(newState.token).toBe("test-token");
      expect(newState.isAuthenticated).toBe(true);
    });

    it("should replace previous user data", () => {
      const oldUser = {
        id: "old-id",
        email: "old@example.com",
        tier: "basic" as const,
      };
      const initialState: AuthState = {
        token: "test-token",
        user: oldUser,
        isAuthenticated: true,
      };
      const newUser = {
        id: "new-id",
        email: "new@example.com",
        tier: "pro" as const,
      };
      const newState = authReducer(initialState, userLoaded(newUser));
      expect(newState.user).toEqual(newUser);
      expect(newState.user?.id).toBe("new-id");
    });
  });

  describe("signedOut action", () => {
    it("should clear all auth state", () => {
      const initialState: AuthState = {
        token: "test-token",
        user: {
          id: "user-1",
          email: "test@example.com",
          tier: "pro" as const,
        },
        isAuthenticated: true,
      };
      const newState = authReducer(initialState, signedOut());
      expect(newState).toEqual({
        token: null,
        user: null,
        isAuthenticated: false,
      });
    });

    it("should idempotently clear state", () => {
      let state: AuthState = authReducer(undefined, { type: "@@INIT" });
      state = authReducer(state, signedOut());
      state = authReducer(state, signedOut());
      expect(state).toEqual({
        token: null,
        user: null,
        isAuthenticated: false,
      });
    });

    it("should work even when already signed out", () => {
      const initialState: AuthState = {
        token: null,
        user: null,
        isAuthenticated: false,
      };
      const newState = authReducer(initialState, signedOut());
      expect(newState).toEqual(initialState);
    });
  });

  describe("integration scenarios", () => {
    it("should handle sign in -> user load -> sign out flow", () => {
      let state: AuthState = authReducer(undefined, { type: "@@INIT" });
      const user = {
        id: "user-1",
        email: "test@example.com",
        tier: "pro" as const,
      };

      state = authReducer(state, signedIn({ token: "token-1" }));
      expect(state.isAuthenticated).toBe(true);

      state = authReducer(state, userLoaded(user));
      expect(state.user).toEqual(user);

      state = authReducer(state, signedOut());
      expect(state).toEqual({
        token: null,
        user: null,
        isAuthenticated: false,
      });
    });

    it("should handle multiple sign in cycles", () => {
      let state: AuthState = authReducer(undefined, { type: "@@INIT" });
      const user1 = {
        id: "user-1",
        email: "user1@example.com",
        tier: "basic" as const,
      };
      const user2 = {
        id: "user-2",
        email: "user2@example.com",
        tier: "pro" as const,
      };

      // First sign in
      state = authReducer(state, signedIn({ token: "token-1", user: user1 }));
      expect(state.user?.id).toBe("user-1");

      // Sign out
      state = authReducer(state, signedOut());
      expect(state.isAuthenticated).toBe(false);

      // Sign in again as different user
      state = authReducer(state, signedIn({ token: "token-2", user: user2 }));
      expect(state.user?.id).toBe("user-2");
    });
  });
});
