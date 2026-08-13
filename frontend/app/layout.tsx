import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Referee",
  description: "Check and revise a paper against real academic databases.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
