import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from 'sonner';
import Landing from "./pages/Landing";
import MapDashboard from "./pages/MapDashboard";
import Navbar from "./components/Navbar";

function Shell() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/map" element={<MapDashboard />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Shell />
        <Toaster position="top-right" richColors closeButton />
      </BrowserRouter>
    </div>
  );
}
