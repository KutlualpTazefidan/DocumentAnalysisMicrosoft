import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function TopBar() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { slug } = useParams<{ slug?: string }>();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="bg-white border-b border-slate-200">
      <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/docs" className="font-semibold text-slate-900">
            Goldens
          </Link>
          <Link to="/local-pdf/inbox" className="px-3 py-1 text-sm hover:underline">
            Local PDF
          </Link>
          {slug ? (
            <>
              <span className="text-slate-400">/</span>
              <span className="text-slate-700">{slug}</span>
            </>
          ) : null}
        </div>
        <button onClick={handleLogout} className="btn-secondary text-sm">
          Abmelden
        </button>
      </div>
    </header>
  );
}
