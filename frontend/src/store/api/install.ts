/** Public, unauthenticated installer script endpoints — plain text/markdown/shell responses. */
import { http } from "./http";

export const installApi = {
  combined: async (): Promise<string> => {
    const { data } = await http.get<string>("/install/flowin-handoff", { responseType: "text" });
    return data;
  },
  command: async (): Promise<string> => {
    const { data } = await http.get<string>("/install/flowin-handoff/command", {
      responseType: "text",
    });
    return data;
  },
  script: async (): Promise<string> => {
    const { data } = await http.get<string>("/install/flowin-handoff/script", {
      responseType: "text",
    });
    return data;
  },
};
