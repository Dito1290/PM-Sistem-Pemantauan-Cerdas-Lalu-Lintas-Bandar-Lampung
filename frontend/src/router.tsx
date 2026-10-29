import { createBrowserRouter } from "react-router-dom";
import { LandingPage } from "./features/landing/LandingPage";
import { LoginPlaceholder } from "./features/auth/LoginPlaceholder";

// Stage 1 ships the landing page. /masuk and the dashboard arrive in stage 2.
export const router = createBrowserRouter([
  { path: "/", element: <LandingPage /> },
  { path: "/masuk", element: <LoginPlaceholder /> },
]);
