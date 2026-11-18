import { createFileRoute } from "@tanstack/react-router";
import { AuthForm } from "@/components/AuthForm";

export const Route = createFileRoute("/signup")({
  head: () => ({
    meta: [
      { title: "Sign up — FORGE AI" },
      { name: "description", content: "Create a FORGE AI account and turn ideas into apps." },
      { property: "og:title", content: "Sign up — FORGE AI" },
      { property: "og:description", content: "Create a FORGE AI account and turn ideas into apps." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => <AuthForm mode="signup" />,
});
