import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CodeCompass | Repository Intelligence",
  description: "Ask questions about your codebase with grounded AI answers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
