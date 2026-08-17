import { configureStore } from "@reduxjs/toolkit";
import authReducer from "@/store/slices/authSlice";
import agentsReducer from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer from "@/store/slices/globalSlice";
import { listenerMiddleware } from "@/store/listenerMiddleware";

export const store = configureStore({
  reducer: {
    auth: authReducer,
    agents: agentsReducer,
    skills: skillsReducer,
    hooks: hooksReducer,
    global: globalReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().prepend(listenerMiddleware.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
