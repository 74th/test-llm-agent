import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { HttpAgent } from "@ag-ui/client";

const runtime = new CopilotRuntime({
  agents: { default: new HttpAgent({ url: `${process.env.AGENT_URL ?? "http://localhost:8000"}/agent/run` }) },
});
const handler = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });
export const GET = handler;
export const POST = handler;
export const OPTIONS = handler;
