import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

export const metadata: Metadata = {
  title: "TubeScout AI — YouTube-powered intelligent product discovery",
  description:
    "TubeScout AI is YouTube-powered intelligent product discovery: multilingual sentiment, aspect analysis, audience clustering, anomaly detection, competitor intelligence and budget optimization — all on live, authorized data.",
  keywords: ["TubeScout AI", "YouTube", "product discovery", "audience intelligence", "sentiment analysis", "campaign", "budget optimizer"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${"antialiased"} bg-background text-foreground`}>
        {children}
        <Toaster />
      </body>
    </html>
  );
}
