import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import Dashboard from "@/pages/Dashboard";
import MissionRoom from "@/pages/MissionRoom";
import History from "@/pages/History";
import WorkforcePage from "@/pages/WorkforcePage";
import Credits from "@/pages/Credits";
import Layout from "@/components/Layout";

function App() {
  return (
    <div className="App dark min-h-screen bg-background text-foreground">
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/history" element={<History />} />
            <Route path="/workforce" element={<WorkforcePage />} />
            <Route path="/credits" element={<Credits />} />
          </Route>
          <Route path="/mission/:id" element={<MissionRoom />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" theme="dark" />
    </div>
  );
}

export default App;
