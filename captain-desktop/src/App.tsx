import { useEffect } from "react";
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from "react-router-dom";
import {
  MessageSquare, Bot, Cpu, Brain, Settings, Wifi, Radio
} from "lucide-react";
import Chat from "./pages/Chat";
import Agents from "./pages/Agents";
import Models from "./pages/Models";
import Memory from "./pages/Memory";
import SettingsPage from "./pages/Settings";
import Accounts from "./pages/Accounts";
import CommandCenter from "./pages/CommandCenter";
import PermissionModal from "./components/PermissionModal";
import { wsClient } from "./lib/ws";

const NAV = [
  { to: "/",               icon: MessageSquare, label: "Chat" },
  { to: "/command-center", icon: Radio,         label: "Command Center" },
  { to: "/agents",         icon: Bot,           label: "Agents" },
  { to: "/models",         icon: Cpu,           label: "Models" },
  { to: "/memory",         icon: Brain,         label: "Memory" },
  { to: "/accounts",       icon: Wifi,          label: "Accounts" },
  { to: "/settings",       icon: Settings,      label: "Settings" },
];

function Sidebar() {
  return (
    <nav className="w-14 flex flex-col items-center py-4 gap-1 bg-zinc-950 border-r border-zinc-800/80">
      {/* Logo */}
      <div className="mb-3 text-xl">⚓</div>

      {NAV.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          title={label}
          className={({ isActive }) =>
            `p-2.5 rounded-xl transition-colors ${
              isActive
                ? "bg-indigo-600/20 text-indigo-400"
                : "text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800"
            }`
          }
        >
          <Icon size={18} />
        </NavLink>
      ))}
    </nav>
  );
}

// Expose navigation to Rust via window globals
function NavigationExposer() {
  const navigate = useNavigate();
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__navigateTo = navigate;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__toggleVoice = () => {
      // Toggle voice via API
      import("./lib/api").then(({ api }) => {
        api.voice.getMode().then(({ mode }) => {
          const next = mode === "disabled" ? "push_to_talk" : "disabled";
          api.voice.setMode(next);
        });
      });
    };
  }, [navigate]);
  return null;
}

export default function App() {
  useEffect(() => {
    wsClient.connect();
    return () => wsClient.disconnect();
  }, []);

  return (
    <BrowserRouter>
      <NavigationExposer />
      <div className="flex h-screen w-screen bg-zinc-950 text-white overflow-hidden font-sans">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/"                element={<Chat />} />
            <Route path="/chat"            element={<Chat />} />
            <Route path="/command-center"  element={<CommandCenter />} />
            <Route path="/agents"          element={<Agents />} />
            <Route path="/models"          element={<Models />} />
            <Route path="/memory"          element={<Memory />} />
            <Route path="/accounts"        element={<Accounts />} />
            <Route path="/settings"        element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
      {/* Global permission approval modal — floats above all pages */}
      <PermissionModal />
    </BrowserRouter>
  );
}
