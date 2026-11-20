import { Link } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";
import { btnPrimary } from "./brand";

/** Landing header actions: the original Log in / Sign up links, or a Dashboard link once signed in. */
export function SessionLinks() {
  const { status } = useAuth();
  if (status === "authenticated") {
    return (
      <Link to="/app" className={`${btnPrimary} px-4 py-2`}>
        Dashboard
      </Link>
    );
  }
  return (
    <>
      <Link to="/login" className="hidden px-3 text-sm font-semibold sm:block">
        Log in
      </Link>
      <Link to="/signup" className={`${btnPrimary} px-4 py-2`}>
        Sign up
      </Link>
    </>
  );
}
