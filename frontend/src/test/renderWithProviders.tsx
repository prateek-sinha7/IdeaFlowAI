import React, { ReactElement } from "react";
import { render, RenderOptions, RenderResult } from "@testing-library/react";
import { Provider } from "react-redux";
import { combineReducers, configureStore } from "@reduxjs/toolkit";
import authReducer from "@/store/slices/authSlice";
import agentsReducer from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer from "@/store/slices/globalSlice";
import { store } from "@/store";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

// Re-export commonly used testing utilities
export { screen, fireEvent, waitFor, within } from "@testing-library/react";

// Combine ONCE into a single root reducer rather than handing `configureStore` a
// reducer *map* alongside `preloadedState`. With a map + preloadedState, Redux 5
// requires every slice reducer to be assignable to
// `Reducer<S, UnknownAction, S | undefined>`, but an RTK `slice.reducer` is typed
// `Reducer<S>` (preloaded state = S, not S | undefined) — so the map form fails to
// typecheck (TS2322). `combineReducers` produces one reducer whose preloaded-state
// parameter is already the partial root state, which is exactly what we pass.
const testRootReducer = combineReducers({
  auth: authReducer,
  agents: agentsReducer,
  skills: skillsReducer,
  hooks: hooksReducer,
  global: globalReducer,
});

type PreloadedRootState = Partial<ReturnType<typeof testRootReducer>>;

interface CustomRenderOptions extends Omit<RenderOptions, "wrapper"> {
  preloadedState?: PreloadedRootState;
  store?: typeof store;
}

// Track the last render result and store for rerenders
let lastRenderResult: RenderResult | null = null;
let lastTestStore: ReturnType<typeof configureStore> | null = null;

/**
 * Custom render function that wraps components with Redux Provider.
 * Use this instead of the standard @testing-library/react render for components
 * that use Redux hooks (useSelector, useDispatch, etc).
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    preloadedState = {},
    store: customStore,
    ...renderOptions
  }: CustomRenderOptions = {}
) {
  // Create a new test store with preloaded state if not provided
  const testStore = customStore ?? configureStore({
    reducer: testRootReducer,
    preloadedState,
  });

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <Provider store={testStore}>
        <SkillsHooksProvider>
          {children}
        </SkillsHooksProvider>
      </Provider>
    );
  }

  const renderResult = render(ui, { wrapper: Wrapper, ...renderOptions });

  // Store for rerenders
  lastRenderResult = renderResult;
  lastTestStore = testStore;

  return renderResult;
}

/**
 * Rerender with the same store as the last render.
 * Use this to update props in tests.
 */
export function rerenderWithProviders(ui: ReactElement) {
  if (!lastRenderResult || !lastTestStore) {
    throw new Error('rerenderWithProviders called before any render');
  }

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <Provider store={lastTestStore!}>
        <SkillsHooksProvider>
          {children}
        </SkillsHooksProvider>
      </Provider>
    );
  }

  lastRenderResult.rerender(
    <Wrapper>{ui}</Wrapper>
  );
}

export default renderWithProviders;
