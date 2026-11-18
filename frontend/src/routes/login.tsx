import { createFileRoute } from "@tanstack/react-router";
import { AuthForm } from "@/components/AuthForm";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Log in — FORGE AI" },
      { name: "description", content: "Log in to FORGE AI and keep building." },
      { property: "og:title", content: "Log in — FORGE AI" },
      { property: "og:description", content: "Log in to FORGE AI and keep building." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => <AuthForm mode="login" />,
});
