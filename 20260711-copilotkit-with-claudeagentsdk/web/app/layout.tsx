import "./style.css";
import { Providers } from "./providers";
export const metadata = { title: "Claude × CopilotKit PoC" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="ja"><body><Providers>{children}</Providers></body></html>;
}
